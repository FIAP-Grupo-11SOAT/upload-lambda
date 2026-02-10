# Processamento de Vídeos com AWS Lambda e FFmpeg

Este projeto implementa uma solução serverless na AWS para processamento de vídeos. A arquitetura utiliza um gatilho do Amazon S3 para invocar uma função AWS Lambda, que por sua vez utiliza FFmpeg para converter e extrair thumbnails de vídeos. Os metadados do processo são armazenados no Amazon DynamoDB.

## Arquitetura

1.  **Upload do Vídeo**: Um arquivo de vídeo é enviado para um bucket S3 de entrada (`upload-bucket-11soat`).
2.  **Invocação da Lambda**: O evento de upload no S3 aciona a função Lambda `upload-function`.
3.  **Processamento do Vídeo**:
    *   A função Lambda baixa o vídeo do S3 para o armazenamento efêmero.
    *   Utilizando uma camada (layer) com FFmpeg, a função:
        *   Converte o vídeo para o formato MP4.
        *   Extrai um thumbnail do vídeo.
    *   Os arquivos processados (vídeo e thumbnail) são salvos em um bucket S3 de destino.
4.  **Armazenamento de Metadados**: A função registra informações sobre o processamento (status, nome do arquivo, etc.) em uma tabela do DynamoDB (`upload`).

## Tecnologias Utilizadas

*   **Computação**: AWS Lambda
*   **Armazenamento**: Amazon S3 e Amazon DynamoDB
*   **Linguagem**: Python 3.11
*   **Infraestrutura como Código (IaC)**: Terraform
*   **Processamento de Mídia**: FFmpeg (disponibilizado como uma Lambda Layer)

## Pré-requisitos

Para implantar e executar este projeto, você precisará ter as seguintes ferramentas instaladas e configuradas:

*   [AWS CLI](https://aws.amazon.com/cli/): Configurado com as credenciais de acesso à sua conta AWS.
*   [Terraform](https://www.terraform.io/downloads.html): Para provisionar a infraestrutura na AWS.
*   [Python 3.11](https://www.python.org/downloads/): Para desenvolvimento e empacotamento da função Lambda.

## Configuração

Antes de implantar, certifique-se de que o ARN da role do IAM e outras variáveis no arquivo `infra/variables.tf` estão corretas para o seu ambiente.

## Implantação (Deploy)

O deploy da infraestrutura e da função Lambda é gerenciado pelo Terraform.

1.  **Navegue até o diretório de infraestrutura**:
    ```bash
    cd infra
    ```

2.  **Inicialize o Terraform**:
    Este comando inicializa o diretório de trabalho, baixando os provedores necessários.
    ```bash
    terraform init
    ```

3.  **Planeje a implantação**:
    Revise os recursos que o Terraform criará.
    ```bash
    terraform plan
    ```

4.  **Aplique a configuração**:
    Este comando provisionará todos os recursos definidos nos arquivos `.tf`.
    ```bash
    terraform apply
    ```
    Confirme a ação digitando `yes` quando solicitado.

## Empacotamento da Função Lambda

A função Lambda precisa ser empacotada em um arquivo `.zip` antes do deploy. O script de deploy do Terraform espera encontrar o arquivo `upload-lambda.zip` no caminho `upload-lambda/src/main/`.

1.  Navegue até o diretório do código-fonte da Lambda:
    ```bash
    cd upload-lambda/src/main
    ```

2.  Crie o arquivo zip:
    ```bash
    zip upload-lambda.zip upload-function.py
    ```

Após criar o zip, execute o `terraform apply` novamente para que o Terraform atualize a função Lambda com o novo pacote.

## Limpeza (Cleanup)

Para remover todos os recursos criados por este projeto e evitar custos contínuos, execute o seguinte comando no diretório `infra`:

```bash
terraform destroy
```
Confirme a ação digitando `yes`.
