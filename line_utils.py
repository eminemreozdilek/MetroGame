import numpy as np
import pyvista as pv


def build_line_actor(coords_list, plotter, color=None):
    if color is None:
        color = [0, 1, 0]
    if len(coords_list) < 2:
        return None
    points_arr = np.array(coords_list, dtype=float)
    spline = pv.Spline(points_arr, 50)
    actor = plotter.add_mesh(spline,
                             color=color,
                             render_lines_as_tubes=True,
                             line_width=5, )
    return actor
