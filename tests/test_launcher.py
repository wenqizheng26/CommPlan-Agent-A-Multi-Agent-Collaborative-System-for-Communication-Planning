import subprocess
import unittest
from unittest import mock
import tempfile
from pathlib import Path
try:
    from launch import model_command
except ImportError:
    model_command = None


IGPU, NVIDIA = 'AMD Radeon(TM) 610M', 'NVIDIA GeForce RTX 4060 Laptop GPU'


class LauncherTests(unittest.TestCase):
    def test_the_gpu_is_chosen_by_name_because_vulkan_numbering_changes_across_reboots(self):
        from launch import resolve_device
        for devices, expected in (([('Vulkan0', NVIDIA), ('Vulkan1', IGPU)], 'Vulkan0'),
                                  ([('Vulkan0', IGPU), ('Vulkan1', NVIDIA)], 'Vulkan1'),
                                  ([('Vulkan0', IGPU)], 'Vulkan0'), ([], 'none')):
            with mock.patch('launch.vulkan_devices', return_value=devices):
                self.assertEqual(resolve_device('llama-server.exe', 'auto'), expected)
        with mock.patch('launch.vulkan_devices', return_value=[('Vulkan0', IGPU), ('Vulkan1', NVIDIA)]):
            self.assertEqual(resolve_device('llama-server.exe', 'nvidia'), 'Vulkan1')
            with self.assertRaisesRegex(RuntimeError, 'Arc'):
                resolve_device('llama-server.exe', 'Arc')
        with mock.patch('launch.vulkan_devices', side_effect=AssertionError('an explicit device is not listed')):
            self.assertEqual(resolve_device('llama-server.exe', 'Vulkan1'), 'Vulkan1')

    def test_device_list_is_read_from_llama_server(self):
        from launch import vulkan_devices
        listing = ('load_backend: loaded Vulkan backend\nAvailable devices:\n'
                   f'  Vulkan0: {NVIDIA} (7956 MiB, 7188 MiB free)\n  Vulkan1: {IGPU} (8043 MiB, 7640 MiB free)\n')
        with mock.patch('launch.subprocess.run', return_value=subprocess.CompletedProcess([], 0, listing, '')):
            self.assertEqual(vulkan_devices('llama-server.exe'), [('Vulkan0', NVIDIA), ('Vulkan1', IGPU)])
        with mock.patch('launch.subprocess.run', side_effect=OSError('not a program')):
            self.assertEqual(vulkan_devices('llama-server.exe'), [])

    def test_pinned_local_model_uses_offline_and_nvidia_device(self):
        self.assertIsNotNone(model_command, '本地启动器尚未实现')
        from planning.providers.registry import Registry
        from launch import RUNTIME
        registry_root = Path(__file__).resolve().parents[1]
        registry = Registry(registry_root)
        model = registry.models[registry.defaults['chat']]
        devices = [('Vulkan0', IGPU), ('Vulkan1', NVIDIA)]
        with tempfile.TemporaryDirectory() as temporary, mock.patch('launch.vulkan_devices', return_value=devices):
            root = Path(temporary)
            weight = root / model['weights']
            executable = root / 'models/signal-formula-qwen3' / RUNTIME
            for path in (weight, executable):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture; never executed')
            args = model_command(root, registry_root=registry_root)
        self.assertIn('--offline', args)
        self.assertEqual(args[args.index('--host')+1], '127.0.0.1')
        self.assertEqual(args[args.index('--device') + 1], 'Vulkan1')
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
