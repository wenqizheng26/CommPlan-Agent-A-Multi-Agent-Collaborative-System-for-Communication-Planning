import unittest
import tempfile
from pathlib import Path
try:
    from launch import model_command
except ImportError:
    model_command = None


class LauncherTests(unittest.TestCase):
    def test_pinned_local_model_uses_offline_and_nvidia_device(self):
        self.assertIsNotNone(model_command, '本地启动器尚未实现')
        from planning.providers.registry import Registry
        from launch import RUNTIME
        registry_root = Path(__file__).resolve().parents[1]
        registry = Registry(registry_root)
        model = registry.models[registry.defaults['chat']]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            weight = root / model['weights']
            executable = root / 'models/signal-formula-qwen3' / RUNTIME
            for path in (weight, executable):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture; never executed')
            args = model_command(root, registry_root=registry_root)
        self.assertIn('--offline', args)
        self.assertEqual(args[args.index('--host')+1], '127.0.0.1')
        self.assertIn('Vulkan1', args)
        from planning.providers.registry import Registry
        registry = Registry(Path(__file__).resolve().parents[1])
        self.assertEqual(registry.defaults['chat'], 'qwen35-9b-q4')
        model = registry.models[registry.defaults['chat']]
        self.assertEqual(args[args.index('--alias') + 1], model['alias'])
        self.assertEqual(args[args.index('--port') + 1], model['endpoint'].rsplit(':', 1)[1])
        self.assertEqual(args[args.index('-c') + 1], str(model['context']))
        self.assertEqual(Path(args[args.index('-m') + 1]), weight)
        self.assertFalse(any(a.startswith('https://') for a in args))


if __name__ == '__main__':
    unittest.main()
