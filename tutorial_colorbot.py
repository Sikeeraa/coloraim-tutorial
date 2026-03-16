import ctypes
from collections import deque
from ctypes import wintypes
import sys
import time

import numpy as np

# ===== CONFIGURAÇÕES DO ALVO =====
# Define a faixa de cor HSV que será procurada (alvo)
LOWER_HSV = np.array([58, 210, 80], dtype=np.uint8)
UPPER_HSV = np.array([63, 255, 255], dtype=np.uint8)

# ===== CONFIGURAÇÕES DE CAPTURA E MIRA =====
CAPTURE_SIZE = (256, 256)          # Tamanho da área capturada no centro da tela
TARGET_HEIGHT = 0.5                 # Altura relativa do ponto de mira no bounding box do alvo (0.5 = meio)
SPEED = 1.0                         # Velocidade do movimento do mouse (multiplicador)
Y_SPEED_MULTIPLIER = 1.0            # Multiplicador adicional para o eixo Y
SMOOTHING = 1.0                     # Suavização do movimento (0 = sem suavização, 1 = máximo)
DILATION_ITERATIONS = 5              # Iterações de dilatação da máscara para unir pixels próximos
MAX_FPS = 60                         # Limite máximo de quadros por segundo

# ===== TECLAS DE ATALHO =====
VK_LMENU = 0xA4   # ALT esquerdo: ativa/desativa a mira (enquanto pressionado)
VK_HOME = 0x24    # Tecla Home: encerra o script completamente

# ===== CONSTANTES DO WINDOWS =====
BI_RGB = 0
DIB_RGB_COLORS = 0
MOUSEEVENTF_MOVE = 0x0001
SRCCOPY = 0x00CC0020

# ===== ESTRUTURAS PARA CAPTURA DE TELA (WIN32) =====
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]

class RGBQUAD(ctypes.Structure):
    _fields_ = [
        ("rgbBlue", wintypes.BYTE),
        ("rgbGreen", wintypes.BYTE),
        ("rgbRed", wintypes.BYTE),
        ("rgbReserved", wintypes.BYTE),
    ]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", RGBQUAD * 1),
    ]

class ScreenCapture:
    """
    Classe responsável por capturar uma região da tela usando GDI (Windows).
    """
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.user32 = ctypes.windll.user32
        self.gdi32 = ctypes.windll.gdi32

        # Configura os tipos de argumentos e retorno das funções (boa prática)
        self.user32.GetDesktopWindow.restype = wintypes.HWND
        self.user32.GetDC.argtypes = [wintypes.HWND]
        self.user32.GetDC.restype = wintypes.HDC
        self.user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        self.user32.ReleaseDC.restype = ctypes.c_int
        self.gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self.gdi32.CreateCompatibleDC.restype = wintypes.HDC
        self.gdi32.DeleteDC.argtypes = [wintypes.HDC]
        self.gdi32.DeleteDC.restype = wintypes.BOOL
        self.gdi32.CreateDIBSection.argtypes = [
            wintypes.HDC,
            ctypes.POINTER(BITMAPINFO),
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p),
            wintypes.HANDLE,
            wintypes.DWORD,
        ]
        self.gdi32.CreateDIBSection.restype = wintypes.HBITMAP
        self.gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        self.gdi32.SelectObject.restype = wintypes.HGDIOBJ
        self.gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        self.gdi32.DeleteObject.restype = wintypes.BOOL
        self.gdi32.BitBlt.argtypes = [
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.DWORD,
        ]
        self.gdi32.BitBlt.restype = wintypes.BOOL

        # Obtém o contexto da área de trabalho
        self.desktop_window = self.user32.GetDesktopWindow()
        self.screen_dc = self.user32.GetDC(self.desktop_window)
        if not self.screen_dc:
            raise OSError("Não foi possível obter o contexto da tela (GetDC)")

        # Cria um contexto de dispositivo compatível em memória
        self.memory_dc = self.gdi32.CreateCompatibleDC(self.screen_dc)
        if not self.memory_dc:
            self.user32.ReleaseDC(self.desktop_window, self.screen_dc)
            raise OSError("Falha ao criar contexto de memória compatível")

        # Prepara a estrutura de informações do bitmap
        bitmap_info = BITMAPINFO()
        bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bitmap_info.bmiHeader.biWidth = self.width
        bitmap_info.bmiHeader.biHeight = -self.height  # valor negativo = imagem top-down
        bitmap_info.bmiHeader.biPlanes = 1
        bitmap_info.bmiHeader.biBitCount = 32
        bitmap_info.bmiHeader.biCompression = BI_RGB

        # Cria uma DIB (Device Independent Bitmap) e obtém o ponteiro para os pixels
        pixel_pointer = ctypes.c_void_p()
        self.bitmap = self.gdi32.CreateDIBSection(
            self.memory_dc,
            ctypes.byref(bitmap_info),
            DIB_RGB_COLORS,
            ctypes.byref(pixel_pointer),
            None,
            0,
        )
        if not self.bitmap or not pixel_pointer.value:
            self.gdi32.DeleteDC(self.memory_dc)
            self.user32.ReleaseDC(self.desktop_window, self.screen_dc)
            raise OSError("Falha ao criar DIB section")

        # Seleciona o bitmap no contexto de memória e guarda o bitmap anterior para restauração
        self.previous_bitmap = self.gdi32.SelectObject(self.memory_dc, self.bitmap)

        # Cria um array numpy que aponta para os pixels do bitmap
        buffer_type = ctypes.c_ubyte * (self.width * self.height * 4)
        self.buffer = np.ctypeslib.as_array(buffer_type.from_address(pixel_pointer.value))
        self.frame = self.buffer.reshape((self.height, self.width, 4))

    def grab(self, left, top):
        """
        Captura a região da tela nas coordenadas (left, top) com o tamanho definido.
        Retorna um array numpy (height, width, 3) com os canais BGR.
        """
        success = self.gdi32.BitBlt(
            self.memory_dc,
            0,
            0,
            self.width,
            self.height,
            self.screen_dc,
            left,
            top,
            SRCCOPY,
        )
        if not success:
            raise OSError("BitBtl falhou ao copiar a tela")
        # Retorna apenas os 3 primeiros canais (BGR) sem o canal alpha
        return self.frame[:, :, :3].copy()

    def close(self):
        """Libera todos os recursos GDI alocados."""
        if getattr(self, "memory_dc", None) and getattr(self, "previous_bitmap", None):
            self.gdi32.SelectObject(self.memory_dc, self.previous_bitmap)
        if getattr(self, "bitmap", None):
            self.gdi32.DeleteObject(self.bitmap)
            self.bitmap = None
        if getattr(self, "memory_dc", None):
            self.gdi32.DeleteDC(self.memory_dc)
            self.memory_dc = None
        if getattr(self, "screen_dc", None):
            self.user32.ReleaseDC(self.desktop_window, self.screen_dc)
            self.screen_dc = None

# ===== FUNÇÕES DE PROCESSAMENTO DE IMAGEM =====
def bgr_to_hsv(frame):
    """
    Converte um frame BGR (numpy array) para os componentes HSV.
    Retorna três arrays: hue (matiz), saturation (saturação), value (valor).
    A implementação é manual para evitar dependência do OpenCV.
    """
    # Normaliza para [0, 1]
    b = frame[:, :, 0].astype(np.float32) / 255.0
    g = frame[:, :, 1].astype(np.float32) / 255.0
    r = frame[:, :, 2].astype(np.float32) / 255.0

    cmax = np.maximum(r, np.maximum(g, b))
    cmin = np.minimum(r, np.minimum(g, b))
    delta = cmax - cmin

    hue = np.zeros_like(cmax)
    non_zero_delta = delta > 0

    # Cálculo do matiz (hue) conforme a fórmula HSV
    red_is_max = non_zero_delta & (cmax == r)
    green_is_max = non_zero_delta & (cmax == g)
    blue_is_max = non_zero_delta & (cmax == b)

    hue[red_is_max] = ((g[red_is_max] - b[red_is_max]) / delta[red_is_max]) % 6
    hue[green_is_max] = ((b[green_is_max] - r[green_is_max]) / delta[green_is_max]) + 2
    hue[blue_is_max] = ((r[blue_is_max] - g[blue_is_max]) / delta[blue_is_max]) + 4
    hue = (hue * 30).astype(np.uint8)  # Converte para 0-180 (padrão OpenCV)

    # Saturação
    saturation = np.zeros_like(cmax)
    non_zero_value = cmax > 0
    saturation[non_zero_value] = delta[non_zero_value] / cmax[non_zero_value]
    saturation = (saturation * 255).astype(np.uint8)

    # Valor (brightness)
    value = (cmax * 255).astype(np.uint8)

    return hue, saturation, value

def build_mask(frame):
    """
    Cria uma máscara booleana com os pixels que estão dentro da faixa HSV definida.
    """
    hue, saturation, value = bgr_to_hsv(frame)
    return (
        (hue >= LOWER_HSV[0]) & (hue <= UPPER_HSV[0]) &
        (saturation >= LOWER_HSV[1]) & (saturation <= UPPER_HSV[1]) &
        (value >= LOWER_HSV[2]) & (value <= UPPER_HSV[2])
    )

def dilate(mask, iterations):
    """
    Aplica dilatação em uma máscara booleana (crescimento dos pixels verdadeiros).
    É uma implementação simples sem usar bibliotecas externas.
    """
    dilated = mask
    height, width = dilated.shape

    for _ in range(iterations):
        expanded = dilated.copy()
        for offset_y in (-1, 0, 1):
            source_y_start = max(0, -offset_y)
            source_y_end = height - max(0, offset_y)
            dest_y_start = max(0, offset_y)
            dest_y_end = height - max(0, -offset_y)

            for offset_x in (-1, 0, 1):
                if offset_x == 0 and offset_y == 0:
                    continue
                source_x_start = max(0, -offset_x)
                source_x_end = width - max(0, offset_x)
                dest_x_start = max(0, offset_x)
                dest_x_end = width - max(0, -offset_x)

                # Propaga os pixels verdadeiros para os vizinhos
                expanded[dest_y_start:dest_y_end, dest_x_start:dest_x_end] |= dilated[
                    source_y_start:source_y_end,
                    source_x_start:source_x_end,
                ]
        dilated = expanded
    return dilated

def get_component_bounds(mask, seed_x, seed_y):
    """
    Encontra os limites (min_x, min_y, max_x, max_y) do componente conectado
    que contém a semente (seed_x, seed_y). A máscara é modificada durante a busca.
    Usa busca em largura (BFS) com deque.
    """
    height, width = mask.shape
    queue = deque([(seed_x, seed_y)])
    mask[seed_y, seed_x] = False  # Marca como visitado

    min_x = max_x = seed_x
    min_y = max_y = seed_y

    while queue:
        x, y = queue.pop()
        # Atualiza os limites
        if x < min_x:
            min_x = x
        if x > max_x:
            max_x = x
        if y < min_y:
            min_y = y
        if y > max_y:
            max_y = y

        # Verifica os 8 vizinhos (incluindo diagonais)
        start_y = max(0, y - 1)
        end_y = min(height, y + 2)
        start_x = max(0, x - 1)
        end_x = min(width, x + 2)

        for next_y in range(start_y, end_y):
            for next_x in range(start_x, end_x):
                if mask[next_y, next_x]:
                    mask[next_y, next_x] = False
                    queue.append((next_x, next_y))

    return min_x, min_y, max_x, max_y

# ===== CLASSE PRINCIPAL DO AIMBOT =====
class SimpleAimbot:
    def __init__(self):
        self.user32 = ctypes.windll.user32
        self.capture_width, self.capture_height = CAPTURE_SIZE

        # Calcula a posição da captura (centro da tela)
        screen_width = self.user32.GetSystemMetrics(0)
        screen_height = self.user32.GetSystemMetrics(1)
        self.capture_left = screen_width // 2 - self.capture_width // 2
        self.capture_top = screen_height // 2 - self.capture_height // 2
        self.capture_center_x = self.capture_width // 2
        self.capture_center_y = self.capture_height // 2

        # Inicializa a captura de tela
        self.capture = ScreenCapture(self.capture_width, self.capture_height)

        # Variáveis para suavização e acumulação de movimento
        self.previous_x = 0.0
        self.previous_y = 0.0
        self.remainder_x = 0.0
        self.remainder_y = 0.0

    def is_key_down(self, virtual_key):
        """Verifica se uma tecla virtual está pressionada no momento."""
        return bool(self.user32.GetAsyncKeyState(virtual_key) & 0x8000)

    def find_target(self, frame):
        """
        Processa o frame e retorna as coordenadas (x, y) do centro do alvo
        relativo ao centro da área de captura, ou None se não encontrado.
        """
        mask = build_mask(frame)
        if not mask.any():
            return None

        # Dilata a máscara para conectar pixels próximos
        mask = dilate(mask, DILATION_ITERATIONS)
        ys, xs = np.nonzero(mask)
        if len(xs) == 0:
            return None

        # Encontra o pixel mais próximo do centro da captura
        distances = (xs - self.capture_center_x) ** 2 + (ys - self.capture_center_y) ** 2
        closest_index = int(np.argmin(distances))
        seed_x = int(xs[closest_index])
        seed_y = int(ys[closest_index])

        # Extrai o componente conectado a partir da semente
        working_mask = mask.copy()
        min_x, min_y, max_x, max_y = get_component_bounds(working_mask, seed_x, seed_y)

        # Calcula o ponto de mira (centro horizontal, e altura proporcional)
        width = max_x - min_x + 1
        height = max_y - min_y + 1
        target_x = min_x + width // 2 - self.capture_center_x
        target_y = int(min_y + height * (1 - TARGET_HEIGHT)) - self.capture_center_y
        return target_x, target_y

    def get_move_amount(self, target):
        """
        Aplica velocidade, suavização e acumula os movimentos fracionários.
        Retorna os deslocamentos inteiros para mover o mouse.
        """
        target_x, target_y = target
        target_x *= SPEED
        target_y *= SPEED * Y_SPEED_MULTIPLIER

        # Suavização exponencial (low-pass filter)
        smoothed_x = self.previous_x * (1 - SMOOTHING) + target_x * SMOOTHING
        smoothed_y = self.previous_y * (1 - SMOOTHING) + target_y * SMOOTHING
        self.previous_x = smoothed_x
        self.previous_y = smoothed_y

        # Adiciona os restos de movimentos anteriores
        smoothed_x += self.remainder_x
        smoothed_y += self.remainder_y

        move_x = int(smoothed_x)
        move_y = int(smoothed_y)
        self.remainder_x = smoothed_x - move_x
        self.remainder_y = smoothed_y - move_y
        return move_x, move_y

    def move_mouse(self, move_x, move_y):
        """Move o mouse relativamente à posição atual."""
        if move_x == 0 and move_y == 0:
            return
        self.user32.mouse_event(MOUSEEVENTF_MOVE, move_x, move_y, 0, 0)

    def reset(self):
        """Reseta as variáveis de suavização e resto."""
        self.previous_x = 0.0
        self.previous_y = 0.0
        self.remainder_x = 0.0
        self.remainder_y = 0.0

    def run(self):
        """
        Loop principal do aimbot.
        Exibe uma única mensagem inicial com as teclas de atalho.
        """
        min_loop_time = 1 / MAX_FPS

        # Mensagem única com status e hotkeys
        print(f"Aimbot rodando. Hotkeys: [ALT] ativar mira, [HOME] sair.")

        try:
            while True:
                loop_start = time.perf_counter()

                # Tecla HOME encerra o script
                if self.is_key_down(VK_HOME):
                    print("Tecla HOME pressionada. Encerrando...")
                    break

                # Se ALT estiver pressionado, procura o alvo e move o mouse
                if self.is_key_down(VK_LMENU):
                    frame = self.capture.grab(self.capture_left, self.capture_top)
                    target = self.find_target(frame)
                    if target is not None:
                        move_x, move_y = self.get_move_amount(target)
                        self.move_mouse(move_x, move_y)
                    else:
                        self.reset()
                else:
                    self.reset()

                # Controle de FPS
                elapsed = time.perf_counter() - loop_start
                if elapsed < min_loop_time:
                    time.sleep(min_loop_time - elapsed)

        finally:
            self.capture.close()

def main():
    # Verifica se está no Windows
    if sys.platform != "win32":
        raise SystemExit("Este script só funciona no Windows.")

    aimbot = SimpleAimbot()
    aimbot.run()

if __name__ == "__main__":
    main()