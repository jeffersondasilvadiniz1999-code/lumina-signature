# Lumina Signature — V2.5 Mobile Teste

Versão de teste da Lumina Signature com os fluxos anteriores preservados e os ajustes finais solicitados:

- Página do cliente responsiva de verdade para celular.
- 2 produtos por linha no celular.
- Categorias lado a lado (2 por linha no celular e 3 em telas intermediárias).
- Correção dos separadores de vírgula que estavam criando células extras no grid.
- Cabeçalho, catálogo, filtros, produto, carrinho e conta adaptados para telas pequenas.
- Filtro de cores mostra apenas cores cadastradas pelo administrador e utilizadas por produtos publicados.
- Cadastro/edição de produto usa seleção por caixas de seleção das cores cadastradas em “Categorias e cores”.
- Backend rejeita cores que não estejam cadastradas.
- Interface de cadastro/gerenciamento de cores mantida.
- Demais funcionalidades da versão anterior preservadas.

## Executar

```powershell
python app.py
```

Abrir no notebook:

`http://127.0.0.1:5000`

Admin:

`http://127.0.0.1:5000/admin`

Para testar no celular, notebook e celular precisam estar na mesma rede Wi-Fi. Use o IPv4 do notebook:

`http://SEU-IP:5000`
