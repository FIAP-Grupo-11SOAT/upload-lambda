import unittest
import json
import os
import sys
import base64
from unittest.mock import patch, MagicMock
import importlib.util

# Carrega o módulo dinamicamente.
# Como estamos em 'tests/', precisamos voltar um nível e entrar em 'src/main'
MODULE_FILE = 'upload-function.py'
MODULE_PATH = os.path.join(os.path.dirname(__file__), '../src/main', MODULE_FILE)

spec = importlib.util.spec_from_file_location("upload_function", MODULE_PATH)
upload_function = importlib.util.module_from_spec(spec)
sys.modules["upload_function"] = upload_function
spec.loader.exec_module(upload_function)

class TestUploadFunction(unittest.TestCase):

    def setUp(self):
        # Configura variáveis de ambiente simuladas no módulo
        upload_function.S3_BUCKET = 'test-bucket'
        upload_function.TABLE_NAME = 'test-table'
        # Silencia logs para não poluir a saída dos testes
        upload_function.logger.setLevel(50)

    def test_validar_extensao(self):
        """Testa a validação de extensões de arquivo."""
        self.assertTrue(upload_function.validar_extensao('video.mp4'))
        self.assertTrue(upload_function.validar_extensao('filme.avi'))
        self.assertFalse(upload_function.validar_extensao('imagem.jpg'))
        self.assertFalse(upload_function.validar_extensao('script.sh'))

    def test_extrair_dados_json_valido(self):
        """Testa a extração de dados quando o input é JSON."""
        event = {
            'body': json.dumps({
                'email': 'teste@email.com',
                'filename': 'video.mp4',
                'arquivo': base64.b64encode(b'conteudo_fake').decode('utf-8')
            })
        }
        email, filename, content = upload_function.extrair_dados_requisicao(event)
        self.assertEqual(email, 'teste@email.com')
        self.assertEqual(filename, 'video.mp4')
        self.assertEqual(content, b'conteudo_fake')

    def test_extrair_dados_json_invalido(self):
        """Testa erro ao receber JSON inválido."""
        event = {'body': '{json quebrado'}
        with self.assertRaises(ValueError):
            upload_function.extrair_dados_requisicao(event)

    @patch('upload_function.boto3')
    @patch('upload_function.subprocess.run')
    @patch('upload_function.shutil.which')
    @patch('upload_function.glob.glob')
    @patch('upload_function.upload_para_s3')
    def test_lambda_handler_sucesso(self, mock_upload_s3, mock_glob, mock_which, mock_run, mock_boto3):
        """Testa o fluxo principal de sucesso da Lambda."""
        # Mock do ffmpeg e sistema de arquivos
        mock_which.return_value = '/usr/bin/ffmpeg'
        mock_run.return_value = MagicMock(returncode=0)
        mock_glob.return_value = ['/tmp/frame1.png', '/tmp/frame2.png']

        # Mock do DynamoDB
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        event = {
            'body': json.dumps({
                'email': 'user@test.com',
                'filename': 'video.mp4',
                'arquivo': base64.b64encode(b'video_bytes').decode('utf-8')
            })
        }

        response = upload_function.lambda_handler(event, None)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertTrue(body['success'])
        self.assertEqual(body['frame_count'], 2)

        # Verifica chamadas aos serviços AWS
        mock_table.put_item.assert_called_once()
        mock_table.update_item.assert_called_once()
        mock_upload_s3.assert_called_once()

    def test_lambda_handler_falha_configuracao(self):
        """Testa falha quando variáveis de ambiente estão ausentes."""
        upload_function.S3_BUCKET = None
        response = upload_function.lambda_handler({}, None)
        self.assertEqual(response['statusCode'], 500)
        self.assertIn('BUCKET', json.loads(response['body'])['message'])

    @patch('upload_function.boto3')
    def test_lambda_handler_extensao_nao_suportada(self, mock_boto3):
        """Testa rejeição de arquivo com extensão inválida."""
        event = {
            'body': json.dumps({
                'email': 'user@test.com',
                'filename': 'virus.exe',
                'arquivo': base64.b64encode(b'lixo').decode('utf-8')
            })
        }
        response = upload_function.lambda_handler(event, None)
        self.assertEqual(response['statusCode'], 400)
        self.assertIn('Formato', json.loads(response['body'])['message'])

if __name__ == '__main__':
    unittest.main()