#!/usr/bin/env python3
"""
This module provides a client for interacting with various LLM APIs using LiteLLM,
with support for an L2 disk cache to persist query/response pairs.
It uses a centralized background event loop to manage concurrency and prevent
file descriptor explosion when using FanoutCache.
"""

import os, time
import logging
import hashlib
import shutil
import json
import asyncio
import threading
import atexit
import math
from pathlib import Path
from typing import Any, List, Optional

try:
    import resource
except ImportError:  # Windows: no POSIX resource module
    resource = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
# --- Cache Management ---

class LlmCacheManager:
    """
    Manages a persistent disk cache for LLM responses using FanoutCache.
    Acts as an L2 cache layer.
    """
    def __init__(self, folder: str, shards: int = 8, size_limit: str = "2GB", reset: bool = False):
        self.folder = folder
        self.shards = shards
        self.size_limit_bytes = self._parse_size_to_bytes(size_limit)
        
        if reset:
            self.clear_cache()

        self.check_file_count()
        self.check_cache_settings()

        try:
            from diskcache import FanoutCache
            self.cache = FanoutCache(
                directory=self.folder, 
                shards=self.shards, 
                size_limit=self.size_limit_bytes
            )
            logger.info(f"LlmCacheManager initialized at {self.folder} (Size limit: {size_limit}, Shards: {shards})")
        except ImportError:
            logger.error("The 'diskcache' package is required for LLM caching. Please run 'pip install diskcache'.")
            self.cache = None

    def check_file_count(self):
        """
        In the new async architecture, only the background event loop thread
        opens connections to the cache. The FD requirement is now much lower.
        Needed FDs = (1 thread * shards * ~3 FDs) + overhead.
        """
        if resource is None:
            return
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        
        # Base requirement: shards * 3 (for SQLite) + room for network sockets and files
        file_count_needed = (self.shards * 3) + 150
        
        if hard < file_count_needed:
            logger.error(f"File count hard limit {hard} is too low. Needed: {file_count_needed}.")
            exit(1)

        if soft < file_count_needed:
            logger.warning(f"File count soft limit {soft} is low. Increasing to {file_count_needed}.")
            try:
                resource.setrlimit(resource.RLIMIT_NOFILE, (file_count_needed, hard))
            except Exception as e:
                logger.error(f"Failed to increase soft limit: {e}")

    def check_cache_settings(self):
        meta_path = os.path.join(self.folder, "cache_meta_data.json")
        
        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'r') as f:
                    meta = json.load(f)
                    ori_shards = meta.get("shards")
                    if ori_shards != self.shards:
                        logger.error(f"Cache shard count mismatch. New: {self.shards}, Old: {ori_shards}.")
                        exit(1)
            except Exception as e:
                logger.warning(f"Could not read cache meta data: {e}. Proceeding.")
        else:
            if os.path.exists(self.folder):
                self.clear_cache()

            os.makedirs(self.folder, exist_ok=True)
            with open(meta_path, 'w') as f:
                json.dump({"shards": self.shards, "size_limit": self.size_limit_bytes}, f)
                
        return True
        
    def _parse_size_to_bytes(self, size_str: str) -> int:
        units = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}
        size_str = size_str.upper().strip()
        
        for unit, multiplier in units.items():
            if size_str.endswith(unit):
                try:
                    number = float(size_str[:-len(unit)])
                    return int(number * multiplier)
                except ValueError:
                    break
        return 2 * 1024**3

    def clear_cache(self):
        logger.info(f"Clearing LLM cache at {self.folder}...")
        if os.path.exists(self.folder):
            try:
                shutil.rmtree(self.folder)
            except Exception as e:
                logger.error(f"Failed to remove cache directory: {e}")
                exit(1)

    def get_instance(self):
        return self.cache

# --- LLM Clients ---

FAKE_SUMMARY_CONTENT = "This part implements important functionalities."

class LlmClient:
    """
    Base class for LLM clients. Manages a singleton background event loop 
    to handle all async operations (API calls and DiskCache) centrally.
    """
    is_local: bool = False
    _worker_loop: Optional[asyncio.AbstractEventLoop] = None
    _worker_thread: Optional[threading.Thread] = None
    _lock = threading.Lock()
    _semaphore: Optional[asyncio.Semaphore] = None

    def __init__(self):
        self.cache = None

    @classmethod
    def launch_worker_thread(cls, concurrency_limit: int):
        """Initializes the background worker thread and event loop exactly once."""
        with cls._lock:
            if cls._worker_thread is None:
                cls._worker_loop = asyncio.new_event_loop()
                cls._semaphore = asyncio.Semaphore(concurrency_limit)
                cls._worker_thread = threading.Thread(
                    target=cls._run_event_loop, 
                    args=(cls._worker_loop,), 
                    daemon=True,
                    name="LlmClientWorker"
                )
                cls._worker_thread.start()
                atexit.register(cls.terminate)
                logger.debug(f"LlmClient background worker thread started with concurrency limit {concurrency_limit}.")

    @staticmethod
    def _run_event_loop(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    @classmethod
    def terminate(cls):
        """Gracefully shuts down the background loop and thread."""
        with cls._lock:
            if cls._worker_loop is not None and cls._worker_loop.is_running():
                cls._worker_loop.call_soon_threadsafe(cls._worker_loop.stop)
                if cls._worker_thread:
                    cls._worker_thread.join(timeout=2)
                cls._worker_loop = None
                cls._worker_thread = None
                logger.info("LlmClient background worker terminated.")

    def enable_system_cache(self, cache_manager: LlmCacheManager):
        self.cache = cache_manager.get_instance()

    def generate_summary(self, prompt: str) -> str:
        """Synchronous entry point that bridges to the async background worker."""
        if self._worker_loop is None or not self._worker_loop.is_running():
            logger.error("LlmClient worker loop is not running.")
            return ""

        future = asyncio.run_coroutine_threadsafe(
            self._async_generate_wrapper(prompt), 
            self._worker_loop
        )
        try:
            # We use a long timeout here as the internal acompletion has its own timeout
            return future.result(timeout=310)
        except Exception as e:
            logger.error(f"LlmClient request failed: {e}")
            return ""

    def get_context_window_size(self) -> int:
        """Returns the maximum input token limit for the model."""
        raise NotImplementedError

    async def _async_generate_wrapper(self, prompt: str) -> str:
        """Internal wrapper to handle caching logic before/after the model call."""
        cache_key = None
        if self.cache is not None:
            prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            cache_key = f"Prompt_hash:{prompt_hash}"
            
            # Non-blocking cache check
            cached_val = await self._worker_loop.run_in_executor(
                None, lambda: self.cache.get(cache_key)
            )
            if cached_val:
                return cached_val

        # Cache miss: Call the implementation-specific generator
        async with self._semaphore:
            content = await self._async_generate(prompt)

        # Save to DiskCache
        if content and self.cache is not None:
            await self._worker_loop.run_in_executor(
                None, lambda: self.cache.set(cache_key, content)
            )
        
        return content

    async def _async_generate(self, prompt: str) -> str:
        """To be implemented by subclasses."""
        raise NotImplementedError

class LiteLlmClient(LlmClient):
    """A unified client for various LLM APIs using LiteLLM."""
    def __init__(self, api_name: str):
        self.api_name = api_name.lower()
        self.is_local = self.api_name == 'ollama'
        super().__init__()
        
        if self.api_name == 'openai':
            self.model_name = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")
        elif self.api_name == 'deepseek':
            self.model_name = os.environ.get("DEEPSEEK_MODEL", "deepseek/deepseek-coder")
        elif self.api_name == 'ollama':
            self.model_name = f"ollama/{os.environ.get('OLLAMA_MODEL', 'deepseek-llm:7b')}"
        else:
            raise ValueError(f"Unsupported API '{self.api_name}' for LiteLlmClient.")

    def get_context_window_size(self) -> int:
        try:
            import litellm

            # get_model_info provides granular limits (input vs output)
            info = litellm.get_model_info(self.model_name)
            return info.get("max_input_tokens") or info.get("max_tokens") or 128000
        except Exception:
            # Fallback for models not in the LiteLLM registry (e.g. some local Ollama models)
            try:
                import litellm

                return litellm.get_max_tokens(self.model_name) or 128000
            except Exception:
                return 128000

    async def _async_generate(self, prompt: str) -> str:
        try:
            import litellm

            response = await litellm.acompletion(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                timeout=300
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LiteLLM acompletion failed for model '{self.model_name}': {e}")
            return ""

class FakeLlmClient(LlmClient):
    """A fake client for debugging that returns a static summary.
    By default, it does not use llm cache even if the cache is turn on, to avoid cache pollution.
    """
    def __init__(self):
        self.api_name = "fake"
        self.is_local = True 
        super().__init__()

    # NOTE: If you want to experiment with the llm cache for fake client, you can simply rename this function,
    # so that it does not override the default `generate_summary` method in the parent class, which will use the cache.
    def generate_summary(self, prompt: str) -> str:
        """Simulate a sync delay and return static text."""
        time.sleep(0.01) 
        return FAKE_SUMMARY_CONTENT

    def get_context_window_size(self) -> int:
        return 128000

    async def _async_generate(self, prompt: str) -> str:
        """Simulate an async delay and return static text."""
        # await asyncio.sleep(0.01) 
        return FAKE_SUMMARY_CONTENT


def get_llm_client(api_name: str) -> LlmClient:
    """Factory function to get an LLM client."""
    api_name = api_name.lower()
    if api_name == 'fake':
        return FakeLlmClient()
    
    try:
        return LiteLlmClient(api_name)
    except ValueError:
         raise ValueError(f"Unknown API: {api_name}. Supported APIs are: openai, deepseek, ollama, fake.")


def setup_llm_client(args, project_path: str) -> LlmClient:
    """
    Factory + Configurator that returns a fully initialized LLM client.
    Handles worker thread launching and system-level (L2) caching.
    """
    client = get_llm_client(args.llm_api)
    
    # 1. Handle Workers (Decide concurrency based on whether client is local or remote)
    num_workers = args.num_local_workers if client.is_local else args.num_remote_workers
    client.launch_worker_thread(num_workers)
    
    # 2. Handle L2 (System) Cache
    if not getattr(args, 'no_llm_cache', False):
        cache_folder = getattr(args, 'llm_cache_folder', None)
        if not cache_folder:
            cache_folder = os.path.join(project_path, ".cache", "llm_cache")
        
        cache_shards = getattr(args, 'llm_cache_shards', None)
        if not cache_shards:
            # Match shards to local workers for performance/concurrency
            cache_shards = args.num_local_workers

        llm_cache_manager = LlmCacheManager(
            folder=cache_folder, 
            shards=cache_shards, 
            size_limit=getattr(args, 'llm_cache_size', "2GB"), 
            reset=getattr(args, 'llm_cache_reset', False)
        )
        client.enable_system_cache(llm_cache_manager)
        
    return client


# --- Embedding Clients ---
# Stays synchronous as it's typically CPU/GPU bound locally.
#
# Environment:
#   SENTENCE_TRANSFORMER_MODEL — HuggingFace id or local path (default: all-MiniLM-L6-v2 → 384 dims).
#     Repo-local offline folder: embedding_models/ + standalone_tools/download_embedding_model.py (see embedding_models/README.md).
#   EMBEDDING_DIMENSION (alias: NEO4J_VECTOR_DIMENSION) — declare vector width for indexes/manifests; must match the model (default 384).
#
# One SentenceTransformer per process (singleton) to avoid loading the model multiple times.


def _repo_local_default_embedding_model() -> Optional[str]:
    """
    If ``embedding_models/sentence-transformers/all-MiniLM-L6-v2`` exists in the repo
    (e.g. copied from a machine with Hugging Face access), use it when ``SENTENCE_TRANSFORMER_MODEL``
    is unset so air-gapped installs never call the Hub.
    """
    try:
        root = Path(__file__).resolve().parent
        local = root / "embedding_models" / "sentence-transformers" / "all-MiniLM-L6-v2"
        if (local / "config.json").is_file():
            return str(local)
    except OSError:
        pass
    return None


class EmbeddingClient:
    """Base class for embedding clients."""
    is_local: bool = False

    def generate_embeddings(self, texts: list[str], show_progress_bar: bool = True) -> list[list[float]]:
        raise NotImplementedError

    def get_embedding_dimension(self) -> int:
        """Vector size produced by ``generate_embeddings``."""
        raise NotImplementedError


class SentenceTransformerClient(EmbeddingClient):
    """Client that uses a local SentenceTransformer model (offline)."""
    is_local: bool = True

    def __init__(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "The 'sentence-transformers' package is required for offline embeddings. "
                "Run: pip install sentence-transformers"
            ) from exc

        model_name = os.environ.get("SENTENCE_TRANSFORMER_MODEL", "").strip()
        if not model_name:
            model_name = _repo_local_default_embedding_model() or "all-MiniLM-L6-v2"
            if model_name != "all-MiniLM-L6-v2":
                logger.info(
                    "SENTENCE_TRANSFORMER_MODEL unset; loading bundled repo weights from %s",
                    model_name,
                )
        logger.info("Loading local SentenceTransformer model: %s", model_name)
        self.model = SentenceTransformer(model_name)
        self._dim: Optional[int] = None

    def get_embedding_dimension(self) -> int:
        if self._dim is None:
            getter = getattr(self.model, "get_embedding_dimension", None) or getattr(
                self.model, "get_sentence_embedding_dimension", None
            )
            if callable(getter):
                self._dim = int(getter())
            else:
                enc_kw: dict[str, Any] = {"show_progress_bar": False, "convert_to_numpy": True}
                dev = os.environ.get("SENTENCE_TRANSFORMER_DEVICE", "").strip()
                if dev:
                    enc_kw["device"] = dev
                probe = self.model.encode(["__embedding_dim_probe__"], **enc_kw)
                self._dim = int(probe.shape[1])
            logger.info("SentenceTransformer embedding dimension: %s", self._dim)
            self._warn_if_declared_embedding_dim_mismatch()
        return self._dim

    def _warn_if_declared_embedding_dim_mismatch(self) -> None:
        env_dims = os.environ.get("EMBEDDING_DIMENSION") or os.environ.get("NEO4J_VECTOR_DIMENSION")
        if env_dims is None:
            return
        try:
            expected = int(env_dims)
        except ValueError:
            logger.warning("Invalid EMBEDDING_DIMENSION / NEO4J_VECTOR_DIMENSION=%r; ignoring.", env_dims)
            return
        if expected != self._dim:
            logger.warning(
                "Embedding model outputs dim=%s but EMBEDDING_DIMENSION/NEO4J_VECTOR_DIMENSION=%s. "
                "Update the env (or pick a matching model) so FAISS/Chroma/JSONL exports and any vector index stay aligned.",
                self._dim,
                expected,
            )

    def generate_embeddings(self, texts: list[str], show_progress_bar: bool = True) -> list[list[float]]:
        if not texts:
            return []
        cleaned: List[str] = []
        for t in texts:
            if t is None:
                s = ""
            else:
                s = str(t).strip()
            if not s:
                s = " "
            cleaned.append(s)

        enc_kw: dict[str, Any] = {"show_progress_bar": show_progress_bar, "convert_to_numpy": True}
        dev = os.environ.get("SENTENCE_TRANSFORMER_DEVICE", "").strip()
        if dev:
            enc_kw["device"] = dev
        embeddings = self.model.encode(cleaned, **enc_kw)
        n = int(embeddings.shape[0])
        if n != len(cleaned):
            raise RuntimeError(
                f"SentenceTransformer.encode returned {n} rows for {len(cleaned)} inputs; "
                "refusing misaligned batch (would corrupt downstream vector files or DB writes)."
            )
        dim = int(embeddings.shape[1])
        if self._dim is None:
            self._dim = dim
            logger.info("SentenceTransformer embedding dimension: %s", self._dim)
            self._warn_if_declared_embedding_dim_mismatch()
        elif dim != self._dim:
            raise RuntimeError(
                f"Inconsistent embedding width: expected {self._dim}, got {dim} (check model / inputs)."
            )

        out: List[List[float]] = []
        for i in range(n):
            row = embeddings[i].tolist()
            if len(row) != dim:
                raise RuntimeError(f"Row {i}: expected length {dim}, got {len(row)}")
            out.append(row)
        return out


_embedding_singleton: Optional[SentenceTransformerClient] = None
_embedding_singleton_lock = threading.Lock()


def get_embedding_client(api_name: str) -> EmbeddingClient:
    """
    Return the process-wide offline embedding client (SentenceTransformer).

    ``api_name`` is kept for callers (e.g. ``\"local\"``, summary engine passing ``llm_api``);
    only the local SentenceTransformer backend exists today.
    """
    if api_name and str(api_name).lower() not in ("local", "default", ""):
        logger.warning(
            "get_embedding_client(%r): only local SentenceTransformer is implemented; ignoring api_name.",
            api_name,
        )
    global _embedding_singleton
    with _embedding_singleton_lock:
        if _embedding_singleton is None:
            logger.info("Initializing local SentenceTransformer client for embeddings (singleton).")
            _embedding_singleton = SentenceTransformerClient()
        return _embedding_singleton


def get_offline_embedding_dimension() -> int:
    """Embedding width for the configured model (loads singleton client if needed)."""
    return get_embedding_client("local").get_embedding_dimension()
