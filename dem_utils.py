import numpy as np
import cv2
import pyvista as pv

def visual_to_elevation(filename):
    height_scale = 0.05
    img = cv2.imread(filename, cv2.IMREAD_ANYDEPTH)
    if img is None:
        raise ValueError(f"Image not found or unable to load: {filename}")
    img_array = np.array(img, dtype=np.float32)
    return img_array * height_scale

def plot_dem_in_pyvista(data, boundaries):
    nx, ny = data.shape
    x_coords = np.linspace(0, boundaries[2]-boundaries[0], nx)
    y_coords = np.linspace(0, boundaries[3]-boundaries[1], ny)
    X, Y = np.meshgrid(x_coords, y_coords, indexing="ij")
    grid = pv.StructuredGrid(X, Y, data)
    grid.point_data["Elevation"] = data.flatten(order="F")
    land = grid.threshold(0.01, scalars="Elevation", invert=False)
    sea = grid.threshold(0.01, scalars="Elevation", invert=True)
    sea.points[:,2] = 0
    return land, sea, x_coords, y_coords, data
