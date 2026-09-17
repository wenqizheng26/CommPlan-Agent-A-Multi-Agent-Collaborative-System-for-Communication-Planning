import unittest
from pathlib import Path
try:
    from launch import model_command
except ImportError:
    model_command = None


class LauncherTests(unittest.TestCase):
    def test_pinned_local_model_uses_offline_and_nvidia_device(self):
        self.assertIsNotNone(model_command, '本地启动器尚未实现')
        args = model_command(Path(__file__).resolve().parents[1])
        self.assertIn('--offline', args)
        self.assertEqual(args[args.index('--host')+1], '127.0.0.1')
        self.assertIn('Vulkan1', args)
        self.assertFalse(any(a.startswith('https://') for a in args))


if __name__ == '__main__':
    unittest.main()
