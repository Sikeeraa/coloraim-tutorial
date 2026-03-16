# SimpleAimbot — Aimbot por Cor (HSV) em Python

[![Python](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/)

Aimbot baseado em visão computacional para fins educacionais.  
Implementa captura de tela via GDI, segmentação por cor (HSV) e movimento suave do mouse.

---

## Sobre o projeto

O SimpleAimbot demonstra como criar um sistema de detecção de alvos utilizando apenas Python e chamadas diretas à API do Windows, sem dependências externas como OpenCV. O código é modular, comentado e projetado para ser compreendido por quem está aprendendo conceitos de captura de tela, processamento de imagem e automação.

---

## Funcionamento

O loop principal executa com controle de FPS. A cada iteração:

- Captura uma região central da tela com GDI (BitBlt).
- Converte a imagem de BGR para HSV através de implementação manual.
- Gera uma máscara binária baseada em uma faixa de cor predefinida.
- Aplica dilatação para conectar pixels próximos.
- Identifica o componente conectado mais próximo do centro.
- Calcula o ponto de mira dentro do bounding box.
- Suaviza o movimento com filtro exponencial e acumula subpixels.
- Move o mouse com `mouse_event`.

A mira só é ativada enquanto a tecla `ALT` estiver pressionada. Ao soltar, as variáveis de suavização são resetadas.

---

## Configurações

Todas as constantes ajustáveis estão no início do arquivo `tutorial_colorbot.py`.

| Parâmetro | Descrição |
|-----------|-----------|
| `LOWER_HSV` / `UPPER_HSV` | Faixa de cor do alvo (H, S, V). |
| `CAPTURE_SIZE` | Dimensões da área de captura (largura, altura). |
| `TARGET_HEIGHT` | Altura relativa do ponto de mira (0.0 = topo, 0.5 = meio, 1.0 = base). |
| `SPEED` | Multiplicador de velocidade do mouse. |
| `Y_SPEED_MULTIPLIER` | Multiplicador adicional para o eixo Y. |
| `SMOOTHING` | Fator de suavização (0 = sem suavização, 1 = máximo amortecimento). |
| `DILATION_ITERATIONS` | Iterações de dilatação da máscara. |
| `MAX_FPS` | Limite de quadros por segundo. |

Para ajustar a cor alvo, utilize um editor de imagens (GIMP, Photoshop) para obter os valores HSV de um pixel do objeto desejado. Considere variações de iluminação ao definir os limites inferior e superior.

---

## Instalação

1. Clone o repositório:
   ```bash
   git clone https://github.com/seu-usuario/simple-aimbot.git
   cd simple-aimbot
