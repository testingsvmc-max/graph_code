import os
import tempfile
import unittest

from index_path_remap import (
    abs_path_to_worker_file_uri,
    file_uri_to_abs_path,
    infer_index_source_root_from_compile_commands_path,
    longest_common_posix_path_prefix,
    make_index_root_to_local_uri_remapper,
    path_from_file_uri_for_remap,
    remap_compile_commands_entries,
)


class TestIndexPathRemap(unittest.TestCase):
    def test_linux_uri_not_mapped_to_drive_home_on_windows(self):
        """Regression: /home/... must not become D:\\home\\... on Windows."""
        uri = "file:///home/dpi/build_server/android/src/foo.cpp"
        p = path_from_file_uri_for_remap(uri)
        self.assertTrue(p.startswith("/home/dpi/"), p)

    def test_roundtrip_abs_uri_style(self):
        p = os.path.abspath(os.path.join(os.getcwd(), "dummy.txt"))
        uri = abs_path_to_worker_file_uri(p)
        self.assertTrue(uri.startswith("file://"))
        back = file_uri_to_abs_path(uri)
        self.assertEqual(os.path.normcase(back), os.path.normcase(p))

    def test_remap_preserves_relative(self):
        base = tempfile.mkdtemp()
        try:
            idx = os.path.join(base, "idx_root")
            loc = os.path.join(base, "loc_root")
            os.makedirs(os.path.join(idx, "src"), exist_ok=True)
            os.makedirs(loc, exist_ok=True)
            src_under_idx = os.path.join(idx, "src", "a.c")
            open(src_under_idx, "w", encoding="utf-8").close()
            uri_in = abs_path_to_worker_file_uri(src_under_idx)
            remap = make_index_root_to_local_uri_remapper(idx, loc)
            out = remap(uri_in)
            expected = abs_path_to_worker_file_uri(os.path.join(loc, "src", "a.c"))
            self.assertEqual(
                os.path.normcase(file_uri_to_abs_path(out)),
                os.path.normcase(file_uri_to_abs_path(expected)),
            )
        finally:
            import shutil

            shutil.rmtree(base, ignore_errors=True)

    def test_remap_compile_commands_no_false_prefix(self):
        """Do not rewrite /proj/android when the path is /proj/android2/..."""
        import pathlib

        loc = pathlib.Path(tempfile.mkdtemp())
        try:
            entries = [
                {
                    "directory": "/home/dpi/qb5_8815/workspace/P4_1716/android2/out",
                    "file": "/home/dpi/qb5_8815/workspace/P4_1716/android2/src/a.cpp",
                    "arguments": [
                        "clang++",
                        "-I/home/dpi/qb5_8815/workspace/P4_1716/android2/include",
                    ],
                }
            ]
            root = "/home/dpi/qb5_8815/workspace/P4_1716/android"
            out = remap_compile_commands_entries(entries, root, loc)
            d0 = out[0]["directory"].replace("\\", "/")
            self.assertIn("/home/dpi", d0)
            self.assertIn("android2", d0)
            self.assertNotIn(str(loc).replace("\\", "/"), d0)
        finally:
            import shutil

            shutil.rmtree(loc, ignore_errors=True)

    def test_longest_common_posix_path_prefix(self):
        self.assertEqual(
            longest_common_posix_path_prefix(
                [
                    "/home/ci/android/frameworks/native/cmds/foo.cpp",
                    "/home/ci/android/packages/apps/Bar/baz.cpp",
                ]
            ),
            "/home/ci/android",
        )
        self.assertEqual(longest_common_posix_path_prefix(["/home/a/b"]), "/home/a/b")

    def test_infer_index_root_from_compile_commands(self):
        import json
        import pathlib

        td = pathlib.Path(tempfile.mkdtemp())
        try:
            cc = td / "compile_commands.json"
            entries = [
                {
                    "directory": "/home/ci/android/out/soong/obj",
                    "file": "/home/ci/android/frameworks/native/cmds/foo.cpp",
                },
                {
                    "directory": "/home/ci/android/out/soong/other",
                    "file": "/home/ci/android/packages/apps/Bar/baz.cpp",
                },
            ]
            cc.write_text(json.dumps(entries), encoding="utf-8")
            root = infer_index_source_root_from_compile_commands_path(str(cc))
            self.assertEqual(root, "/home/ci/android")
        finally:
            import shutil

            shutil.rmtree(td, ignore_errors=True)

    def test_remap_compile_commands_android_tree(self):
        import pathlib

        loc = pathlib.Path(tempfile.mkdtemp())
        try:
            entries = [
                {
                    "directory": "/home/dpi/proj/build",
                    "file": "/home/dpi/proj/src/a.cpp",
                    "arguments": ["clang++", "-I/home/dpi/proj/include", "/home/dpi/proj/src/a.cpp"],
                }
            ]
            out = remap_compile_commands_entries(entries, "/home/dpi/proj", loc)
            loc_s = str(loc).replace("\\", "/")
            self.assertNotIn("/home/dpi", out[0]["directory"].replace("\\", "/"))
            self.assertTrue(out[0]["directory"].replace("\\", "/").startswith(loc_s), out[0]["directory"])
            self.assertTrue(out[0]["file"].replace("\\", "/").startswith(loc_s), out[0]["file"])
            joined = " ".join(str(x) for x in out[0]["arguments"])
            self.assertNotIn("/home/dpi", joined.replace("\\", "/"))
        finally:
            import shutil

            shutil.rmtree(loc, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
