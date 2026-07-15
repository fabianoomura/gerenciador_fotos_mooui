# Política de segurança

## Escopo

Este projeto foi desenhado para execução local ou em uma rede privada confiável. A
API escuta em `127.0.0.1` por padrão e exige `CATALOGO_API_TOKEN`. O proxy Next.js
mantém esse token no servidor.

O token protege a API interna, mas não substitui autenticação de usuários na
interface. Antes de qualquer exposição externa, coloque a aplicação atrás de HTTPS,
controle de identidade, limitação de requisições e registros de auditoria.

## Dados que nunca devem ser versionados

- bancos SQLite reais;
- fotografias ou thumbnails do acervo;
- arquivos `.env` e `config.local.ps1`;
- credenciais SMB/CIFS;
- logs operacionais;
- modelos baixados e ambientes virtuais.

## Relato de vulnerabilidades

Não abra uma issue pública com credenciais ou detalhes exploráveis. Use o recurso
**Private vulnerability reporting** do GitHub deste repositório.

Inclua descrição, impacto, versão afetada e passos mínimos para reprodução. Não
inclua fotografias ou dados pessoais reais.
