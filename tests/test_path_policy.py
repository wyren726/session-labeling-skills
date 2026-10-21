import tempfile, unittest
from pathlib import Path
from session_labeling.path_policy import PathPolicy, PathPolicyError
class TestPathPolicy(unittest.TestCase):
 def test_lexical_old_to_new_mapping_without_io(self):
  p=PathPolicy(["/safe/new"],new_root="/safe/new",forbidden_root="/unsafe/old")
  self.assertEqual(str(p.remap_locator("/unsafe/old/wispaper/a.jsonl")),"/safe/new/wispaper/a.jsonl")
 def test_outside_rejected(self):
  p=PathPolicy(["/safe/new"],new_root="/safe/new")
  with self.assertRaises(PathPolicyError): p.remap_locator("/etc/passwd")
 def test_write_outside_rejected(self):
  p=PathPolicy(["/safe/new"],new_root="/safe/new")
  with self.assertRaises(PathPolicyError): p.validate_for_write("/tmp/out.json")
 def test_symlink_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); real=root/"real"; real.mkdir(); (real/"x").write_text("x")
   (root/"link").symlink_to(real,target_is_directory=True)
   p=PathPolicy([root],new_root=root)
   with self.assertRaises(PathPolicyError): p.validate_for_read(root/"link/x")
