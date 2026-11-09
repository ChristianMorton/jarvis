from jarvis.actions.grid import GridOverlay


def test_cells_are_numbered_left_to_right_top_to_bottom():
    grid = GridOverlay(rows=3, cols=3)
    grid.rect = (0, 0, 900, 900)
    assert grid.cell_rect(1)[:2] == (0, 0)
    assert grid.cell_rect(3)[:2] == (600, 0)
    assert grid.cell_rect(5)[:2] == (300, 300)
    assert grid.cell_rect(9)[:2] == (600, 600)


def test_zooming_narrows_the_rectangle():
    grid = GridOverlay(rows=3, cols=3)
    grid.rect = (0, 0, 1920, 1080)
    for _ in range(3):
        grid.rect = grid.cell_rect(5)
    x, y, w, h = grid.rect
    # Three picks on a 3x3 grid is a 27th of each axis: precise enough to click.
    assert w < 75 and h < 45


def test_out_of_range_cell_is_rejected():
    grid = GridOverlay(rows=3, cols=3)
    grid.rect = (0, 0, 900, 900)
    for cell in (0, 10, -1):
        try:
            grid.cell_rect(cell)
        except ValueError:
            continue
        raise AssertionError(f"cell {cell} should have been rejected")
