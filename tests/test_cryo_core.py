import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import json

# Adiciona o diretório 'src' ao sys.path para podermos importar o cryo_core
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import cryo_core


class TestCryoCore(unittest.TestCase):

    def setUp(self):
        # Cria um diretório temporário para testes de escrita de arquivos reais
        self.test_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.test_dir.cleanup()

    def test_get_config_path_frozen(self):
        """Testa se _get_config_path detecta corretamente o sistema congelado."""
        with patch('os.path.ismount') as mock_ismount:
            mock_ismount.return_value = True
            path, is_frozen = cryo_core._get_config_path()
            self.assertEqual(path, cryo_core.CONFIG_PATH_RO)
            self.assertTrue(is_frozen)
            mock_ismount.assert_called_once_with(cryo_core.MOUNT_POINT_RO)

    def test_get_config_path_thawed(self):
        """Testa se _get_config_path detecta corretamente o sistema descongelado."""
        with patch('os.path.ismount') as mock_ismount:
            mock_ismount.return_value = False
            path, is_frozen = cryo_core._get_config_path()
            self.assertEqual(path, cryo_core.CONFIG_PATH_RW)
            self.assertFalse(is_frozen)
            mock_ismount.assert_called_once_with(cryo_core.MOUNT_POINT_RO)

    def test_write_overlayroot_active_line(self):
        """Testa _write_overlayroot quando já existe uma linha overlayroot ativa."""
        config_file = os.path.join(self.test_dir.name, "overlayroot.conf")
        initial_content = (
            "# Arquivo de configuracao\n"
            "overlayroot=\"\"\n"
            "OUTRA_VARIAVEL=\"valor\"\n"
        )
        with open(config_file, "w") as f:
            f.write(initial_content)

        err = cryo_core._write_overlayroot(config_file, "tmpfs:swap=1")
        self.assertIsNone(err)

        with open(config_file, "r") as f:
            content = f.read()

        expected = (
            "# Arquivo de configuracao\n"
            "overlayroot=\"tmpfs:swap=1\"\n"
            "OUTRA_VARIAVEL=\"valor\"\n"
        )
        self.assertEqual(content, expected)

    def test_write_overlayroot_commented_line(self):
        """Testa _write_overlayroot substituindo a linha comentada caso não haja ativa."""
        config_file = os.path.join(self.test_dir.name, "overlayroot.conf")
        initial_content = (
            "# Arquivo de configuracao\n"
            "#overlayroot=\"\"\n"
            "OUTRA_VARIAVEL=\"valor\"\n"
        )
        with open(config_file, "w") as f:
            f.write(initial_content)

        err = cryo_core._write_overlayroot(config_file, "tmpfs:swap=1")
        self.assertIsNone(err)

        with open(config_file, "r") as f:
            content = f.read()

        expected = (
            "# Arquivo de configuracao\n"
            "overlayroot=\"tmpfs:swap=1\"\n"
            "OUTRA_VARIAVEL=\"valor\"\n"
        )
        self.assertEqual(content, expected)

    def test_write_overlayroot_append(self):
        """Testa _write_overlayroot adicionando ao final caso não exista a linha."""
        config_file = os.path.join(self.test_dir.name, "overlayroot.conf")
        initial_content = (
            "# Arquivo de configuracao\n"
            "OUTRA_VARIAVEL=\"valor\"\n"
        )
        with open(config_file, "w") as f:
            f.write(initial_content)

        err = cryo_core._write_overlayroot(config_file, "tmpfs:swap=1")
        self.assertIsNone(err)

        with open(config_file, "r") as f:
            content = f.read()

        expected = (
            "# Arquivo de configuracao\n"
            "OUTRA_VARIAVEL=\"valor\"\n"
            "overlayroot=\"tmpfs:swap=1\"\n"
        )
        self.assertEqual(content, expected)

    def test_write_overlayroot_nonexistent(self):
        """Testa erro caso o arquivo de configuração não exista."""
        config_file = os.path.join(self.test_dir.name, "nonexistent.conf")
        err = cryo_core._write_overlayroot(config_file, "tmpfs:swap=1")
        self.assertIn("ERRO: Arquivo de configuração não encontrado", err)

    def test_get_overlay_usage_inactive(self):
        """Testa get_overlay_usage quando o overlay não está ativo."""
        with patch('os.path.exists') as mock_exists, patch('os.path.ismount') as mock_ismount:
            mock_exists.return_value = False
            mock_ismount.return_value = False
            usage = cryo_core.get_overlay_usage()
            self.assertFalse(usage["active"])

    def test_get_overlay_usage_active(self):
        """Testa get_overlay_usage com sucesso em um sistema ativo."""
        mock_stat = MagicMock()
        mock_stat.f_blocks = 1000
        mock_stat.f_frsize = 4096
        mock_stat.f_bfree = 400

        with patch('os.path.exists') as mock_exists, \
             patch('os.path.ismount') as mock_ismount, \
             patch('os.statvfs', create=True) as mock_statvfs:
            
            mock_exists.return_value = True
            mock_ismount.return_value = True
            mock_statvfs.return_value = mock_stat

            usage = cryo_core.get_overlay_usage()
            self.assertTrue(usage["active"])
            self.assertEqual(usage["total"], 4096000)
            self.assertEqual(usage["free"], 1638400)
            self.assertEqual(usage["used"], 2457600)
            self.assertEqual(usage["percent"], 60.0)

    def test_get_status_json(self):
        """Testa se get_status_json retorna os campos esperados."""
        config_file = os.path.join(self.test_dir.name, "overlayroot.conf")
        with open(config_file, "w") as f:
            f.write('overlayroot="tmpfs:swap=1"\n')

        with patch('os.path.ismount') as mock_ismount, \
             patch('os.path.exists') as mock_exists, \
             patch('cryo_core.CONFIG_PATH_RO', config_file), \
             patch('cryo_core.CONFIG_PATH_RW', config_file), \
             patch('cryo_core.get_overlay_usage') as mock_usage:
            
            mock_ismount.return_value = True
            mock_exists.return_value = True
            mock_usage.return_value = {"active": True, "percent": 50.0}

            status_str = cryo_core.get_status_json()
            status = json.loads(status_str)

            self.assertEqual(status["version"], cryo_core.__version__)
            self.assertTrue(status["is_frozen"])
            self.assertTrue(status["configured_frozen"])
            self.assertTrue(status["maintenance_pending"])
            self.assertTrue(status["maintenance_active"])
            self.assertEqual(status["overlay"]["percent"], 50.0)


if __name__ == '__main__':
    unittest.main()
