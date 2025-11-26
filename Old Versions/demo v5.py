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
PATH_COLOR = (0, 120, 255)  # Route (Blue)
PICKER_COLOR = (255, 0, 255)  # The Worker (Magenta) - FOR ANIMATION
TEXT_COLOR = (255, 255, 255)

UI_BG = (40, 40, 40)
BUTTON_COLOR = (70, 70, 70)
BUTTON_HOVER = (100, 100, 100)

pygame.init()
window = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("Warehouse Picking Simulation")
font = pygame.font.SysFont('Arial', 16)
header_font = pygame.font.SysFont('Arial', 20, bold=True)
number_font = pygame.font.SysFont('Arial', 14, bold=True)


class Button:
    def __init__(self, x, y, width, height, text, callback):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.callback = callback
        self.color = BUTTON_COLOR

    def draw(self, win):
        mouse_pos = pygame.mouse.get_pos()
        if self.rect.collidepoint(mouse_pos):
            pygame.draw.rect(win, BUTTON_HOVER, self.rect)
        else:
            pygame.draw.rect(win, self.color, self.rect)

        text_surf = font.render(self.text, True, TEXT_COLOR)
        text_rect = text_surf.get_rect(center=self.rect.center)
        win.blit(text_surf, text_rect)
        pygame.draw.rect(win, (100, 100, 100), self.rect, 2)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
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

    def draw(self, win, x_offset, in_path=False, is_picker=False):
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
        elif in_path:
            color = PATH_COLOR

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
visible_path_cells = set()  # What is currently drawn
animation_queue = []  # The full calculated path waiting to be drawn
current_picker_node = None  # The 'head' of the animation
is_animating = False


def create_grid():
    global grid, start_box, targets, visible_path_cells, animation_queue, is_animating
    grid = []
    targets = []
    visible_path_cells = set()
    animation_queue = []
    is_animating = False

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
    return path[::-1]  # Return Start -> End


def calculate_tour_distance(tour, dist_matrix):
    total_dist = 0
    for i in range(len(tour) - 1):
        u_idx = tour[i]
        v_idx = tour[i + 1]
        dist = dist_matrix[u_idx][v_idx]['dist']
        if dist == float('inf'): return float('inf')
        total_dist += dist
    return total_dist


def apply_two_opt(tour, dist_matrix):
    best_tour = tour[:]
    best_distance = calculate_tour_distance(best_tour, dist_matrix)
    improved = True

    while improved:
        improved = False
        for i in range(1, len(best_tour) - 2):
            for j in range(i + 1, len(best_tour)):
                if j - i == 1: continue

                new_tour = best_tour[:]
                new_tour[i:j] = best_tour[i:j][::-1]
                new_dist = calculate_tour_distance(new_tour, dist_matrix)

                if new_dist < best_distance:
                    best_tour = new_tour
                    best_distance = new_dist
                    improved = True
    return best_tour


def solve_tsp():
    global animation_queue, is_animating, targets, visible_path_cells

    if not targets:
        Tk().wm_withdraw()
        messagebox.showinfo("Info", "Add some pick locations (Right Click) first.")
        return

    # Clear previous run
    visible_path_cells = set()
    animation_queue = []

    # 1. Build Distance Matrix
    nodes_of_interest = [start_box] + targets
    n_count = len(nodes_of_interest)
    matrix = [[None for _ in range(n_count)] for _ in range(n_count)]

    for i in range(n_count):
        dists, parents = bfs_distance_map(nodes_of_interest[i])
        for j in range(n_count):
            target_node = nodes_of_interest[j]
            if target_node in dists:
                matrix[i][j] = {'dist': dists[target_node], 'parents': parents}
            else:
                matrix[i][j] = {'dist': float('inf'), 'parents': None}

    # 2. Greedy Nearest Neighbor
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

    # 3. Apply 2-Opt
    optimized_tour = apply_two_opt(tour, matrix)

    # 4. Prepare Animation Queue (Don't draw yet)
    for k in range(len(optimized_tour) - 1):
        u_idx = optimized_tour[k]
        v_idx = optimized_tour[k + 1]

        start_node = nodes_of_interest[u_idx]
        end_node = nodes_of_interest[v_idx]
        parent_map = matrix[u_idx][v_idx]['parents']

        # Get segment and add to queue
        segment = get_path_between(start_node, end_node, parent_map)
        for cell in segment:
            animation_queue.append(cell)

        # Update Target Index
        if v_idx != 0:
            targets[v_idx - 1].target_index = k + 1

    # Start the animation loop
    is_animating = True


def main():
    global start_box, visible_path_cells, targets, is_animating, current_picker_node

    create_grid()

    btn_solve = Button(25, 100, 230, 50, "Run Simulation", solve_tsp)
    btn_reset = Button(25, 170, 230, 50, "Reset Warehouse", full_reset)

    clock = pygame.time.Clock()

    while True:
        # Loop Speed (Controls animation speed)
        clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            btn_solve.handle_event(event)
            btn_reset.handle_event(event)

            if not is_animating and any(pygame.mouse.get_pressed()):
                mx, my = pygame.mouse.get_pos()
                if mx > SIDEBAR_WIDTH:
                    grid_x = (mx - SIDEBAR_WIDTH) // BOX_WIDTH
                    grid_y = my // BOX_HEIGHT

                    if 0 <= grid_x < COLUMNS and 0 <= grid_y < ROWS:
                        clicked_box = grid[grid_x][grid_y]
                        keys = pygame.key.get_pressed()
                        if pygame.mouse.get_pressed()[1] or (pygame.mouse.get_pressed()[0] and keys[pygame.K_s]):
                            if clicked_box not in targets and not clicked_box.wall:
                                if start_box: start_box.start = False
                                start_box = clicked_box
                                start_box.start = True
                                start_box.wall = False
                                visible_path_cells = set()
                        elif pygame.mouse.get_pressed()[2]:
                            if clicked_box != start_box and not clicked_box.wall:
                                if clicked_box not in targets:
                                    clicked_box.target = True
                                    targets.append(clicked_box)
                                else:
                                    clicked_box.target = False
                                    clicked_box.target_index = -1
                                    targets.remove(clicked_box)
                                visible_path_cells = set()
                        elif pygame.mouse.get_pressed()[0]:
                            if clicked_box != start_box and clicked_box not in targets:
                                clicked_box.wall = True
                                visible_path_cells = set()

        # --- ANIMATION LOGIC ---
        if is_animating:
            if len(animation_queue) > 0:
                # Process a few frames at once for speed, or 1 for smooth slow motion
                for _ in range(2):  # Process 2 steps per frame (adjustable speed)
                    if len(animation_queue) > 0:
                        next_box = animation_queue.pop(0)
                        visible_path_cells.add(next_box)
                        current_picker_node = next_box
            else:
                is_animating = False  # Done

        # --- DRAWING ---
        window.fill(UI_BG)

        title = header_font.render("WAREHOUSE SIMULATION", True, TEXT_COLOR)
        window.blit(title, (25, 25))
        sub = font.render("Greedy NN + 2-Opt", True, (200, 200, 200))
        window.blit(sub, (25, 50))

        y_off = 300
        controls = [
            ("Left Click: Draw Shelves", WALL_COLOR),
            ("Right Click: Add Order Item", TARGET_COLOR),
            ("Middle / 'S': Set Depot", START_COLOR),
            ("Magenta Box: Active Picker", PICKER_COLOR)
        ]

        window.blit(header_font.render("CONTROLS", True, TEXT_COLOR), (25, y_off - 30))
        for text, col in controls:
            s = font.render(text, True, col)
            window.blit(s, (25, y_off))
            y_off += 30

        btn_solve.draw(window)
        btn_reset.draw(window)

        pygame.draw.rect(window, (0, 0, 0), (SIDEBAR_WIDTH, 0, GRID_WIDTH, WINDOW_HEIGHT))

        for i in range(COLUMNS):
            for j in range(ROWS):
                box = grid[i][j]

                is_path = box in visible_path_cells
                is_picker = (box == current_picker_node and is_animating)

                box.draw(window, SIDEBAR_WIDTH, is_path, is_picker)

        pygame.display.flip()


main()