import pygame
import sys
from tkinter import messagebox, Tk
import collections

# --- Configuration ---
COLUMNS = 38
ROWS = 38

WINDOW_HEIGHT = 760
SIDEBAR_WIDTH = 280
GRID_WIDTH = 760
WINDOW_WIDTH = SIDEBAR_WIDTH + GRID_WIDTH

BOX_WIDTH = GRID_WIDTH // COLUMNS
BOX_HEIGHT = WINDOW_HEIGHT // ROWS

# --- Colors ---
EMPTY_COLOR = (20, 20, 20)  # Background
WALL_COLOR = (240, 240, 240)  # Shelves
START_COLOR = (255, 140, 0)  # Depot (Orange)
TARGET_COLOR = (0, 200, 200)  # Item (Teal)
PICKING_PATH_COLOR = (0, 120, 255)  # Outbound Route (Blue)
RETURN_PATH_COLOR = (50, 205, 50)  # Return Route (Lime Green)
PICKER_COLOR = (255, 0, 255)  # The Worker (Magenta)
TEXT_COLOR = (255, 255, 255)

UI_BG = (40, 40, 40)
BUTTON_COLOR = (70, 70, 70)
BUTTON_HOVER = (100, 100, 100)
BUTTON_DISABLED = (50, 50, 50)  # Dim color for disabled buttons

pygame.init()
window = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("Warehouse Picking: Manual Return Trigger")
font = pygame.font.SysFont('Arial', 16)
header_font = pygame.font.SysFont('Arial', 20, bold=True)
number_font = pygame.font.SysFont('Arial', 14, bold=True)


class Button:
    def __init__(self, x, y, width, height, text, callback, enabled=True):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.callback = callback
        self.enabled = enabled
        self.color = BUTTON_COLOR

    def draw(self, win):
        # Determine visual style based on state
        draw_color = self.color
        text_color = TEXT_COLOR

        if not self.enabled:
            draw_color = BUTTON_DISABLED
            text_color = (100, 100, 100)  # Dim text
        elif self.rect.collidepoint(pygame.mouse.get_pos()):
            draw_color = BUTTON_HOVER

        pygame.draw.rect(win, draw_color, self.rect)

        text_surf = font.render(self.text, True, text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        win.blit(text_surf, text_rect)

        # Border
        border_col = (100, 100, 100) if self.enabled else (60, 60, 60)
        pygame.draw.rect(win, border_col, self.rect, 2)

    def handle_event(self, event):
        if self.enabled and event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.rect.collidepoint(event.pos):
                self.callback()


class Box:
    def __init__(self, i, j):
        self.x = i
        self.y = j
        self.start = False
        self.wall = False
        self.target = False
        self.target_index = -1
        self.neighbours = []
        self.parent = None

    def draw(self, win, x_offset, path_type=None, is_picker=False):
        color = EMPTY_COLOR

        # Priority of colors (what draws on top of what)
        if is_picker:
            color = PICKER_COLOR
        elif self.wall:
            color = WALL_COLOR
        elif self.start:
            color = START_COLOR
        elif self.target:
            color = TARGET_COLOR
        elif path_type == "PICKING":
            color = PICKING_PATH_COLOR
        elif path_type == "RETURN":
            color = RETURN_PATH_COLOR

        draw_x = x_offset + (self.x * BOX_WIDTH)
        draw_y = self.y * BOX_HEIGHT

        pygame.draw.rect(win, color, (draw_x, draw_y, BOX_WIDTH - 2, BOX_HEIGHT - 2))

        if self.target and self.target_index > 0:
            text = number_font.render(str(self.target_index), True, (0, 0, 0))
            text_rect = text.get_rect(center=(draw_x + BOX_WIDTH // 2, draw_y + BOX_HEIGHT // 2))
            win.blit(text, text_rect)

    def set_neighbours(self, grid):
        self.neighbours = []
        if self.x > 0: self.neighbours.append(grid[self.x - 1][self.y])
        if self.x < COLUMNS - 1: self.neighbours.append(grid[self.x + 1][self.y])
        if self.y > 0: self.neighbours.append(grid[self.x][self.y - 1])
        if self.y < ROWS - 1: self.neighbours.append(grid[self.x][self.y + 1])


# --- Global State ---
grid = []
start_box = None
targets = []

# Animation State
visible_path_cells = {}
active_queue = []  # The queue currently being animated
return_queue = []  # Stored sequence for the return trip
current_picker_node = None
is_animating = False
current_algo_name = "Ready"
ready_for_return = False  # Flag to enable the return button


def create_grid():
    global grid, start_box, targets, visible_path_cells, active_queue, return_queue, is_animating, current_algo_name, ready_for_return
    grid = []
    targets = []
    visible_path_cells = {}
    active_queue = []
    return_queue = []
    is_animating = False
    ready_for_return = False
    current_algo_name = "Ready"

    for i in range(COLUMNS):
        arr = []
        for j in range(ROWS):
            arr.append(Box(i, j))
        grid.append(arr)

    for i in range(COLUMNS):
        for j in range(ROWS):
            grid[i][j].set_neighbours(grid)

    start_box = grid[0][0]
    start_box.start = True


def full_reset():
    create_grid()


def bfs_distance_map(start_node):
    for col in grid:
        for box in col:
            box.parent = None

    distances = {start_node: 0}
    parents = {start_node: None}

    q = collections.deque([start_node])
    visited = {start_node}

    while q:
        current = q.popleft()
        for neighbor in current.neighbours:
            if neighbor not in visited and not neighbor.wall:
                visited.add(neighbor)
                neighbor.parent = current
                distances[neighbor] = distances[current] + 1
                parents[neighbor] = current
                q.append(neighbor)
    return distances, parents


def get_path_between(start_node, end_node, parent_map):
    path = []
    curr = end_node
    while curr != start_node and curr is not None:
        path.append(curr)
        curr = parent_map.get(curr)
    return path[::-1]


def trigger_return_trip():
    """Moves data from return_queue to active_queue to start animation"""
    global active_queue, return_queue, is_animating, ready_for_return

    if return_queue:
        active_queue = return_queue[:]  # Copy
        return_queue = []  # Clear
        is_animating = True
        ready_for_return = False  # Disable button while running


def run_simulation(mode):
    global active_queue, return_queue, is_animating, targets, visible_path_cells, current_algo_name, ready_for_return

    if not targets:
        Tk().wm_withdraw()
        messagebox.showinfo("Info", "Add some pick locations (Right Click) first.")
        return

    # Reset State
    visible_path_cells = {}
    active_queue = []
    return_queue = []
    ready_for_return = False
    current_algo_name = "Picking: " + mode

    for t in targets:
        t.target_index = -1

    nodes_of_interest = [start_box] + targets
    n_count = len(nodes_of_interest)

    # Build Matrix
    matrix = [[None for _ in range(n_count)] for _ in range(n_count)]
    for i in range(n_count):
        dists, parents = bfs_distance_map(nodes_of_interest[i])
        for j in range(n_count):
            target_node = nodes_of_interest[j]
            if target_node in dists:
                matrix[i][j] = {'dist': dists[target_node], 'parents': parents}
            else:
                matrix[i][j] = {'dist': float('inf'), 'parents': None}

    # Determine Tour
    tour = []
    if mode == "SEQUENCE":
        tour = list(range(n_count))
    elif mode == "GREEDY":
        unvisited = set(range(1, n_count))
        current_idx = 0
        tour = [0]
        while unvisited:
            best_dist = float('inf')
            nearest_node = -1
            for candidate in unvisited:
                d = matrix[current_idx][candidate]['dist']
                if d < best_dist:
                    best_dist = d
                    nearest_node = candidate

            if nearest_node == -1:
                Tk().wm_withdraw()
                messagebox.showerror("Error", "Some targets are unreachable!")
                return

            tour.append(nearest_node)
            unvisited.remove(nearest_node)
            current_idx = nearest_node

    # --- Construct OUTBOUND (Picking) Path ---
    for k in range(len(tour) - 1):
        u_idx = tour[k]
        v_idx = tour[k + 1]

        start_node = nodes_of_interest[u_idx]
        end_node = nodes_of_interest[v_idx]
        parent_map = matrix[u_idx][v_idx]['parents']

        segment = get_path_between(start_node, end_node, parent_map)
        for cell in segment:
            active_queue.append((cell, "PICKING"))

        if v_idx != 0:
            targets[v_idx - 1].target_index = k + 1

    # --- Construct RETURN Path (Store in separate queue) ---
    last_idx = tour[-1]
    start_idx = 0

    start_node = nodes_of_interest[last_idx]
    end_node = nodes_of_interest[start_idx]
    parent_map = matrix[last_idx][start_idx]['parents']

    return_segment = get_path_between(start_node, end_node, parent_map)
    for cell in return_segment:
        return_queue.append((cell, "RETURN"))

    is_animating = True


def main():
    global start_box, visible_path_cells, targets, is_animating, current_picker_node, current_algo_name, ready_for_return

    create_grid()

    # Buttons
    btn_dijkstra = Button(25, 100, 230, 45, "Run Dijkstra's", lambda: run_simulation("SEQUENCE"))
    btn_greedy = Button(25, 155, 230, 45, "Run Greedy Nearest Neighbour", lambda: run_simulation("GREEDY"))

    # Return Button (Initially Disabled)
    btn_return = Button(25, 210, 230, 45, "Return to Depot", trigger_return_trip, enabled=False)

    btn_reset = Button(25, 270, 230, 45, "Reset Warehouse", full_reset)

    clock = pygame.time.Clock()

    while True:
        clock.tick(60)

        # Update Return Button State
        # It is enabled ONLY if we are NOT animating AND we have a return path waiting
        btn_return.enabled = (not is_animating) and (len(return_queue) > 0)

        # If the return queue is waiting, update the status text
        if btn_return.enabled:
            current_algo_name = "Pick Complete. Return?"
        elif len(return_queue) == 0 and not is_animating and visible_path_cells:
            current_algo_name = "Cycle Complete"

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            btn_dijkstra.handle_event(event)
            btn_greedy.handle_event(event)
            btn_return.handle_event(event)
            btn_reset.handle_event(event)

            if not is_animating and any(pygame.mouse.get_pressed()):
                mx, my = pygame.mouse.get_pos()
                if mx > SIDEBAR_WIDTH:
                    grid_x = (mx - SIDEBAR_WIDTH) // BOX_WIDTH
                    grid_y = my // BOX_HEIGHT

                    if 0 <= grid_x < COLUMNS and 0 <= grid_y < ROWS:
                        clicked_box = grid[grid_x][grid_y]
                        keys = pygame.key.get_pressed()

                        # Reset data if user edits grid
                        if any(pygame.mouse.get_pressed()):
                            pass

                        if pygame.mouse.get_pressed()[1] or (pygame.mouse.get_pressed()[0] and keys[pygame.K_s]):
                            if clicked_box not in targets and not clicked_box.wall:
                                if start_box: start_box.start = False
                                start_box = clicked_box
                                start_box.start = True
                                start_box.wall = False
                                visible_path_cells = {}
                        elif pygame.mouse.get_pressed()[2]:
                            if clicked_box != start_box and not clicked_box.wall:
                                if clicked_box not in targets:
                                    clicked_box.target = True
                                    targets.append(clicked_box)
                                else:
                                    clicked_box.target = False
                                    clicked_box.target_index = -1
                                    targets.remove(clicked_box)
                                visible_path_cells = {}
                        elif pygame.mouse.get_pressed()[0]:
                            if clicked_box != start_box and clicked_box not in targets:
                                clicked_box.wall = True
                                visible_path_cells = {}

        # --- ANIMATION UPDATE ---
        if is_animating:
            if len(active_queue) > 0:
                for _ in range(2):
                    if len(active_queue) > 0:
                        next_box, type_flag = active_queue.pop(0)
                        visible_path_cells[next_box] = type_flag
                        current_picker_node = next_box
            else:
                is_animating = False

        # --- DRAWING ---
        window.fill(UI_BG)

        title = header_font.render("WAREHOUSE LOGISTICS", True, TEXT_COLOR)
        window.blit(title, (25, 25))

        # Status Text logic
        status_col = (200, 200, 200)
        if "Greedy" in current_algo_name:
            status_col = (0, 255, 0)
        elif "Pick Complete" in current_algo_name:
            status_col = (255, 255, 0)

        status = font.render(current_algo_name, True, status_col)
        window.blit(status, (25, 55))

        y_off = 380
        controls = [
            ("Left Click: Draw Shelves", WALL_COLOR),
            ("Right Click: Add Order Item", TARGET_COLOR),
            ("Middle / 'S': Set Depot", START_COLOR),
            ("Blue Line: Picking Path", PICKING_PATH_COLOR),
            ("Green Line: Return to Depot", RETURN_PATH_COLOR)
        ]

        window.blit(header_font.render("CONTROLS", True, TEXT_COLOR), (25, y_off - 30))
        for text, col in controls:
            s = font.render(text, True, col)
            window.blit(s, (25, y_off))
            y_off += 30

        btn_dijkstra.draw(window)
        btn_greedy.draw(window)
        btn_return.draw(window)
        btn_reset.draw(window)

        pygame.draw.rect(window, (0, 0, 0), (SIDEBAR_WIDTH, 0, GRID_WIDTH, WINDOW_HEIGHT))

        for i in range(COLUMNS):
            for j in range(ROWS):
                box = grid[i][j]

                path_type = visible_path_cells.get(box)
                # Keep picker visible if animating OR if it's the end of the line
                is_picker = False
                if is_animating and box == current_picker_node:
                    is_picker = True
                elif not is_animating and current_picker_node == box and visible_path_cells:
                    # Keep showing picker at the last spot when stopped
                    is_picker = True

                box.draw(window, SIDEBAR_WIDTH, path_type, is_picker)

        pygame.display.flip()


main()