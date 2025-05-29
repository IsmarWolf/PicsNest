# PicsNest
Meu aplicativo de gerenciamento de fotos
      
# PicsNest - Gerenciador de Mídia

O PicsNest é um aplicativo de desktop projetado para ajudar você a gerenciar, visualizar e organizar suas coleções locais de fotos e vídeos com uma interface gráfica intuitiva.

## 🌟 Funcionalidades

### Funcionalidade Principal
*   **GUI Multiplataforma:** Construído com Tkinter para ampla compatibilidade.
*   **Suporte Versátil de Mídia:**
    *   **Imagens:** PNG, JPG, JPEG, GIF, BMP, TIFF, WEBP
    *   **Vídeos:** MP4, AVI, MOV, MKV, WMV, FLV (requer VLC e python-vlc)
*   **Navegação por Pastas:** Navegue facilmente pelo seu sistema de arquivos.
*   **Visualização em Grade de Miniaturas:** Visualize rapidamente prévias de suas mídias.
    *   **Carregamento Preguiçoso (Lazy Loading):** Carrega miniaturas em lotes de forma eficiente para melhor desempenho.
    *   **Miniaturas de Vídeo:** Gera miniaturas para arquivos de vídeo (requer OpenCV).
*   **Visualizadores Integrados:**
    *   **Visualizador de Imagens:** Uma janela dedicada para visualizar imagens com navegação (anterior/próximo) e opções de exclusão.
    *   **Visualizador de Vídeos:** Uma janela dedicada para reprodução de vídeo com controles (reproduzir/pausar, buscar, volume, anterior/próximo, excluir) (requer VLC e python-vlc).
*   **Seleção e Pré-visualização:**
    *   Seleção de itens com um clique ou com "laço" (rubber-band).
    *   Painel de pré-visualização detalhado para itens selecionados (imagem/frame de vídeo).
    *   Exibição de informações: nome do arquivo, tamanho, tipo e origem identificada (ex: "Captura de Tela", "Download").
*   **Operações de Arquivo:**
    *   **Excluir:** Move itens para uma lixeira temporária do aplicativo (`.app_trash_v3`). A lixeira é esvaziada ao fechar o aplicativo.
    *   **Desfazer Exclusão:** Restaura itens excluídos recentemente da lixeira.
    *   **Renomear:** Renomeie facilmente arquivos e pastas (atalho F2).
    *   **Abrir com o Sistema:** Opção para abrir arquivos com o aplicativo padrão do sistema.

### Ferramentas Avançadas e Organização
*   **Encontrar Imagens Similares:**
    *   Verifica a pasta atual em busca de imagens visualmente similares usando dhash (requer `imagehash`).
    *   Opção para filtrar e visualizar apenas grupos de imagens similares.
*   **Identificar Capturas de Tela/Downloads:**
    *   Identifica heuristicamente imagens que provavelmente são capturas de tela ou arquivos baixados com base em padrões de nome de arquivo e dados EXIF.
    *   Permite filtrar para mostrar apenas esses itens identificados.
*   **Consolidar Mídias:**
    *   Reúne todas as mídias (imagens/vídeos) de uma pasta raiz selecionada (e suas subpastas) em uma única pasta de destino.
    *   Opções para mover ou copiar arquivos.
    *   Lida com conflitos de nome de arquivo (renomear, pular, sobrescrever).
*   **Organizar Mídias por Data:**
    *   Organiza mídias de uma pasta raiz em uma hierarquia de diretórios estruturada por `Ano/Mês` em uma pasta de destino.
    *   Usa a data de criação EXIF ou a data de modificação do arquivo.
    *   Opções para mover ou copiar arquivos.
    *   Renomeia arquivos com um padrão `DD-HHMMSS_NomeOriginal_seq.ext`.
*   **Separar Arquivos por Tipo:**
    *   Move ou copia automaticamente capturas de tela identificadas para uma subpasta "Screenshots" e vídeos para uma subpasta "Videos" dentro da raiz atual.
*   **Ações em Massa para Itens Similares/Com Erro:**
    *   **Auto-Excluir Similares:** Exclui inteligentemente uma parte das imagens de grupos similares identificados (mantendo aproximadamente metade).
    *   **Excluir/Mover Itens com Erro:** Gerencia itens que falharam ao carregar (ex: arquivos corrompidos, miniaturas ilegíveis).
*   **Filtragem:**
    *   Filtra a visualização por imagens, vídeos ou ambos.
    *   Filtra para mostrar apenas imagens similares.
    *   Filtra para mostrar apenas capturas de tela/downloads identificados.

### Personalização
*   **Cor de Destaque:** Personalize a cor de destaque da interface do usuário do aplicativo.
*   **Ícones Personalizados para Pastas:** Defina ícones de miniatura personalizados para pastas específicas.
*   **Fundos Personalizados para Pastas:** Aplique cores de fundo personalizadas às representações de pastas na grade.
*   **Interface Temática:** Interface com tema escuro para visualização confortável.

## ⚙️ Dependências e Instalação

O PicsNest é um aplicativo Python.

1.  **Python:** Certifique-se de ter o Python 3.x instalado.
2.  **Biblioteca Obrigatória:**
    *   **Pillow (Fork do PIL):** Para processamento de imagens.
        
        pip install Pillow
        
3.  **Bibliotecas Opcionais (para funcionalidades aprimoradas):**
    *   **python-vlc:** Para reprodução de vídeo no visualizador dedicado.
        
        pip install python-vlc
        
        *Nota: Você também precisa ter o VLC media player instalado no seu sistema para que o `python-vlc` funcione corretamente.*
    *   **imagehash:** Para a funcionalidade "Encontrar Imagens Similares".
        
        pip install imagehash
        
    *   **opencv-python:** Para gerar miniaturas de vídeo.
        
        pip install opencv-python
        
    O aplicativo exibirá avisos na inicialização se essas bibliotecas opcionais não forem encontradas, e as funcionalidades relacionadas serão desativadas.

4.  **Clone o Repositório (ou baixe o código-fonte):**
    
    git clone https://github.com/seu_usuario/picsnest.git
    cd picsnest
    
    (Substitua `seu_usuario/picsnest.git` pelo URL real do seu repositório)

## ▶️ Como Executar

Após instalar o Python e as bibliotecas necessárias, navegue até o diretório raiz do projeto no seu terminal e execute:

python main.py

    

IGNORE_WHEN_COPYING_START
Use code with caution. Markdown
IGNORE_WHEN_COPYING_END

O aplicativo deve iniciar, e você pode começar selecionando uma pasta raiz para gerenciar.
🛠️ Configuração

O PicsNest armazena algumas configurações do usuário localmente no mesmo diretório dos scripts do aplicativo:

    theme_settings.json: Salva a cor de destaque da interface do usuário escolhida.

    folder_thumbs.json: Armazena caminhos para ícones de pasta personalizados e configurações de cor de fundo personalizadas.

    .custom_folder_icons/: Um diretório onde cópias de ícones de pasta personalizados são armazenadas.

    .app_trash_v3/: Um diretório temporário para itens excluídos. É esvaziado quando o aplicativo é fechado.

💡 Melhorias Futuras (Ideias Potenciais)

    Marcação (tagging) e edição de metadados.

    Pesquisa e filtragem avançadas (por intervalo de datas, resolução, etc.).

    Integração com banco de dados para varredura mais rápida da biblioteca em execuções subsequentes.

    Suporte para mais tipos de mídia ou formatos de imagem RAW.

    Modo de apresentação de slides.

    Operações de processamento em lote (ex: redimensionar, converter).

🤝 Contribuindo

Contribuições são bem-vindas! Se você tiver ideias para melhorias ou encontrar bugs, sinta-se à vontade para abrir uma issue ou enviar um pull request.

(Opcional: Adicione diretrizes de contribuição mais específicas, se as tiver.)
📜 Licença

(Especifique a licença do seu projeto aqui. Ex: Licença MIT, GPLv3, etc. Se você não escolheu uma, pode considerar adicionar uma como a Licença MIT.)

Exemplo:
Este projeto está licenciado sob a Licença MIT - veja o arquivo LICENSE.md para detalhes.

      

    
