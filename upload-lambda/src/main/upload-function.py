import os
import json
import time
import base64
import tempfile
import subprocess
import zipfile
import glob
import logging
import re
from pathlib import Path
import shutil
from email import policy
from email.parser import BytesParser

import boto3
from uuid import uuid4
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

S3_BUCKET = os.environ.get('BUCKET')
TABLE_NAME = os.environ.get('TABLE')

def lambda_handler(event, context):
    """Handler Lambda para upload e processamento de vídeo.

    Espera um `event['body']` JSON com campos:
      - email: email do usuario
      - filename: nome do arquivo
      - arquivo: conteúdo do arquivo em base64
    Ou multipart/form-data.

    Retorna JSON com resultado em português.
    """
    if not S3_BUCKET:
        return responder(500, {'success': False, 'message': 'Variável de ambiente BUCKET não configurada'})
    if not TABLE_NAME:
        return responder(500, {'success': False, 'message': 'Variável de ambiente TABLE não configurada'})

    try:
        email, nome_arquivo, arquivo_bytes = extrair_dados_requisicao(event)
    except ValueError as e:
        return responder(400, {'success': False, 'message': str(e)})

    if not validar_extensao(nome_arquivo):
        return responder(400, {'success': False, 'message': 'Formato não suportado'})

    timestamp = time.strftime('%Y%m%d_%H%M%S')
    tmp_dir = tempfile.mkdtemp(prefix='proc_')
    upload_id = uuid4().hex
    record_id = f"{email}_{upload_id}"

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(TABLE_NAME)

    try:
        criar_registro_inicial(table, email, upload_id)
    except Exception as e:
        logger.exception('Erro ao gravar DynamoDB inicial')
        return responder(500, {'success': False, 'message': 'Erro ao gravar registro inicial no banco: ' + str(e)})

    try:
        video_path = salvar_video_local(tmp_dir, nome_arquivo, arquivo_bytes, timestamp)
        frames = extrair_frames(video_path, tmp_dir)

        if not frames:
            return responder(500, {'success': False, 'message': 'Nenhum frame extraído do vídeo'})

        zip_path, zip_nome = criar_arquivo_zip(frames, tmp_dir, timestamp)

        s3_key = f'outputs/{zip_nome}'
        upload_para_s3(zip_path, S3_BUCKET, s3_key)

        atualizar_registro_concluido(table, email, upload_id, s3_key, len(frames))

        imagens = [os.path.basename(f) for f in frames]

        return responder(200, {
            'success': True,
            'message': f'Processamento concluído! {len(frames)} frames extraídos.',
            'record_id': record_id,
            's3_key': s3_key,
            'frame_count': len(frames),
            'images': imagens
        })

    except Exception as e:
        logger.exception('Erro no processamento')
        return responder(500, {'success': False, 'message': 'Erro interno: ' + str(e)})
    finally:
        limpar_diretorio_temporario(tmp_dir)


def extrair_dados_requisicao(event):
    headers = {k.lower(): v for k, v in (event.get('headers') or {}).items()}
    content_type = headers.get('content-type')

    email = None
    nome_arquivo = None
    arquivo_bytes = None

    if content_type and 'multipart/form-data' in content_type:
        raw_body = event.get('body') or ''
        body_bytes = base64.b64decode(raw_body) if event.get('isBase64Encoded') else raw_body.encode('utf-8')

        try:
            # Simula um cabeçalho HTTP para usar o parser de email nativo do Python
            headers_bytes = f"Content-Type: {content_type}\r\n\r\n".encode('utf-8')
            msg = BytesParser(policy=policy.default).parsebytes(headers_bytes + body_bytes)
        except Exception:
            raise ValueError('Erro ao parsear multipart/form-data')

        for part in msg.iter_parts():
            name = part.get_param('name', header='content-disposition')
            filename = part.get_filename()

            if filename:
                nome_arquivo = filename
                arquivo_bytes = part.get_payload(decode=True)
            elif name == 'email':
                email = part.get_payload(decode=True).decode('utf-8')
    else:
        try:
            body = json.loads(event.get('body') or '{}')
        except Exception:
            raise ValueError('Corpo inválido: esperado JSON ou multipart/form-data')

        email = body.get('email')
        nome_arquivo = body.get('filename')
        arquivo_b64 = body.get('arquivo')
        if arquivo_b64:
            try:
                arquivo_bytes = base64.b64decode(arquivo_b64)
            except Exception:
                raise ValueError('Arquivo base64 inválido')

    if not email or not nome_arquivo or not arquivo_bytes:
        raise ValueError('Parâmetros ausentes: email, filename e arquivo são obrigatórios')

    return email, nome_arquivo, arquivo_bytes

def validar_extensao(nome_arquivo):
    ext = Path(nome_arquivo).suffix.lower()
    return ext in {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm'}

def criar_registro_inicial(table, email, upload_id):
    table.put_item(Item={
        'idEmail': email,
        'idUpload': upload_id,
        'status': 'processando',
        'created_at': datetime.now(timezone.utc).isoformat()
    })

def salvar_video_local(tmp_dir, nome_arquivo, arquivo_bytes, timestamp):
    video_path = os.path.join(tmp_dir, f"{timestamp}_{nome_arquivo}")
    with open(video_path, 'wb') as f:
        f.write(arquivo_bytes)
    return video_path

def obter_caminho_ffmpeg():
    """Tenta localizar o executável do ffmpeg no sistema."""
    if shutil.which('ffmpeg'):
        return 'ffmpeg'

    # Verifica locais comuns em ambientes Lambda (Layers ou enviado no pacote)
    caminhos_possiveis = ['/opt/bin/ffmpeg', '/var/task/ffmpeg', './ffmpeg']
    for path in caminhos_possiveis:
        if os.path.exists(path) and os.access(path, os.X_OK):
            return path

    return 'ffmpeg' # Retorna o padrão, o que causará erro se não existir

def extrair_frames(video_path, tmp_dir):
    frames_dir = os.path.join(tmp_dir, 'frames')
    os.makedirs(frames_dir, exist_ok=True)
    frame_pattern = os.path.join(frames_dir, 'frame_%04d.png')

    ffmpeg_cmd = obter_caminho_ffmpeg()
    cmd = [ffmpeg_cmd, '-i', video_path, '-vf', 'fps=1', '-y', frame_pattern]
    proc = subprocess.run(cmd, capture_output=True)

    if proc.returncode != 0:
        raise Exception(f"Erro no ffmpeg: {proc.stderr.decode(errors='ignore')}")

    return sorted(glob.glob(os.path.join(frames_dir, '*.png')))

def criar_arquivo_zip(frames, tmp_dir, timestamp):
    zip_nome = f'frames_{timestamp}.zip'
    zip_path = os.path.join(tmp_dir, zip_nome)
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for fpath in frames:
            zf.write(fpath, arcname=os.path.basename(fpath))
    return zip_path, zip_nome

def upload_para_s3(file_path, bucket, key):
    s3 = boto3.client('s3')
    s3.upload_file(file_path, bucket, key)

def atualizar_registro_concluido(table, email, upload_id, s3_key, frame_count):
    table.update_item(
        Key={'idEmail': email, 'idUpload': upload_id},
        UpdateExpression='SET s3_key = :k, #st = :s, frame_count = :fc',
        ExpressionAttributeNames={'#st': 'status'},
        ExpressionAttributeValues={':k': s3_key, ':s': 'Concluido', ':fc': frame_count}
    )

def limpar_diretorio_temporario(tmp_dir):
    try:
        shutil.rmtree(tmp_dir)
    except Exception:
        pass


def responder(status_code, body_dict):
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(body_dict)
    }