import sys
import numpy as np
import cv2
import rasterio
import pyvista as pv
from pyproj import Transformer
import random

from PySide6 import QtWidgets, QtCore, QtGui
from pyvistaqt import QtInteractor

# --- Utility Functions ---

def bounds_to_meters(min_lon, min_lat, max_lon, max_lat):
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    min_x, min_y = transformer.transform(min_lon, min_lat)
    max_x, max_y = transformer.transform(max_lon, max_lat)
    return (min_x, min_y, max_x, max_y)

def visual_to_elevation(filename):
    height_scale = 0.1
    img = cv2.imread(filename, cv2.IMREAD_ANYDEPTH)
    if img is None:
        raise ValueError("Image not found or unable to load.")
    img_array = np.array(img)
    return img_array * height_scale

def plot_dem_in_pyvista(data, boundaries):
    # Compute coordinate arrays
    nx, ny = data.shape
    x_coords = np.linspace(0, boundaries[2] - boundaries[0], nx)
    y_coords = np.linspace(0, boundaries[3] - boundaries[1], ny)
    X, Y = np.meshgrid(x_coords, y_coords, indexing="ij")
    grid = pv.StructuredGrid(X, Y, data)
    grid.point_data["Elevation"] = data.flatten(order="F")
    # Split grid into land and sea
    land = grid.threshold(0.01, scalars="Elevation", invert=False)
    sea = grid.threshold(0.01, scalars="Elevation", invert=True)
    sea.points[:, 2] = 0  # sea level
    return land, sea, x_coords, y_coords, data

# --- Dialog to Select Stations for a Train Line ---
class StationSelectionDialog(QtWidgets.QDialog):
    def __init__(self, station_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Stations for New Train Line")
        self.resize(300, 400)
        self.selected_ids = []
        layout = QtWidgets.QVBoxLayout(self)
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        for sid, (x, y, z) in station_data.items():
            item = QtWidgets.QListWidgetItem(f"Station {sid}  [X: {x:.2f}, Y: {y:.2f}, Z: {z:.2f}]")
            item.setData(QtCore.Qt.UserRole, sid)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(btn_box)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)

    def accept(self):
        self.selected_ids = [item.data(QtCore.Qt.UserRole) for item in self.list_widget.selectedItems()]
        super().accept()

# --- Main UI Application ---
class TrainLineUI(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super(TrainLineUI, self).__init__(parent)
        self.setWindowTitle("Train Line Editor")
        self.resize(1600, 900)

        # Dictionaries to store station and line data.
        # Stations: key = station id (int), value = {'coords': [x, y, z], 'actor': marker actor}
        self.stations = {}
        # Lines: key = line id (int), value = {'station_ids': [list of station ids], 'actor': spline actor, 'color': [r,g,b]}
        self.train_lines = {}
        self.next_station_id = 1
        self.next_line_id = 0

        # --- Set up central widget and layouts ---
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QHBoxLayout(central_widget)

        # PyVista plotter widget
        self.plotter_widget = QtInteractor(self)
        main_layout.addWidget(self.plotter_widget.interactor, stretch=3)

        # Right-side control panel
        control_panel = QtWidgets.QFrame()
        control_panel.setFixedWidth(350)
        cp_layout = QtWidgets.QVBoxLayout(control_panel)
        main_layout.addWidget(control_panel, stretch=1)

        # Station Table
        cp_layout.addWidget(QtWidgets.QLabel("Stations (ID, X, Y, Z):"))
        self.station_table = QtWidgets.QTableWidget(0, 4)
        self.station_table.setHorizontalHeaderLabels(["ID", "X", "Y", "Z"])
        self.station_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        cp_layout.addWidget(self.station_table)

        # Buttons for station operations
        station_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_add_station = QtWidgets.QPushButton("Add Station (Click on Plot)")
        self.btn_del_station = QtWidgets.QPushButton("Delete Station")
        station_btn_layout.addWidget(self.btn_add_station)
        station_btn_layout.addWidget(self.btn_del_station)
        cp_layout.addLayout(station_btn_layout)

        # Line Table
        cp_layout.addWidget(QtWidgets.QLabel("Train Lines (ID, Station IDs):"))
        self.line_table = QtWidgets.QTableWidget(0, 2)
        self.line_table.setHorizontalHeaderLabels(["Line ID", "Station IDs"])
        self.line_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        cp_layout.addWidget(self.line_table)

        # Buttons for line operations
        line_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_add_line = QtWidgets.QPushButton("Add Train Line")
        self.btn_edit_line = QtWidgets.QPushButton("Edit Train Line")
        self.btn_del_line = QtWidgets.QPushButton("Delete Line")
        line_btn_layout.addWidget(self.btn_add_line)
        line_btn_layout.addWidget(self.btn_edit_line)
        line_btn_layout.addWidget(self.btn_del_line)
        cp_layout.addLayout(line_btn_layout)
        cp_layout.addStretch()

        # Connect signals
        self.btn_add_station.clicked.connect(self.instruct_add_station)
        self.btn_del_station.clicked.connect(self.delete_station)
        self.btn_add_line.clicked.connect(self.add_line)
        self.btn_edit_line.clicked.connect(self.edit_line)
        self.btn_del_line.clicked.connect(self.delete_line)
        self.station_table.cellChanged.connect(self.station_cell_changed)
        self.line_table.cellChanged.connect(self.line_cell_changed)

        # --- Set up the DEM and plot it ---
        self.setup_dem()

        # Enable point picking for station addition.
        self.plotter_widget.enable_point_picking(callback=self.point_picked, use_picker=True)

    def setup_dem(self):
        # For demonstration, we use the visual_to_elevation function on a sample file.
        boundaries = (0, 0, 100000, 100000)
        try:
            dem_data = visual_to_elevation("gradient_map.tiff")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))
            return
        land, sea, self.x_coords, self.y_coords, self.dem_data = plot_dem_in_pyvista(dem_data, boundaries)
        self.plotter_widget.add_mesh(land, show_edges=False, cmap="binary")
        self.plotter_widget.add_mesh(sea, show_edges=False, color="navy")
        self.plotter_widget.show_grid()
        self.plotter_widget.reset_camera()

    def get_elevation(self, x, y):
        # Use nearest neighbor search in DEM grid.
        i = np.abs(self.x_coords - x).argmin()
        j = np.abs(self.y_coords - y).argmin()
        return self.dem_data[i, j]

    def instruct_add_station(self):
        QtWidgets.QMessageBox.information(self, "Add Station",
            "Click anywhere on the plot to add a train station.")

    def point_picked(self, point, p2):
        """Callback when a point is picked in the plotter."""
        if point is None:
            return
        # Determine elevation from DEM (update z using DEM)
        x, y = point[0], point[1]
        z = self.get_elevation(x, y)
        coords = [x, y, z]
        sid = self.next_station_id
        self.next_station_id += 1

        # Add a marker to the plotter and store its actor
        marker = self.plotter_widget.add_point_labels([coords], [f"Station {sid}"],
                                                      point_size=20, font_size=12)
        self.stations[sid] = {"coords": coords, "actor": marker}

        # Update the station table.
        row = self.station_table.rowCount()
        self.station_table.insertRow(row)
        for col, value in enumerate([sid, x, y, z]):
            item = QtWidgets.QTableWidgetItem(f"{value:.2f}" if col != 0 else str(value))
            if col == 0:
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.station_table.setItem(row, col, item)

    def station_cell_changed(self, row, column):
        # When user edits X or Y, update Z to the DEM's elevation.
        if column not in [1, 2]:
            return
        try:
            sid = int(self.station_table.item(row, 0).text())
            x = float(self.station_table.item(row, 1).text())
            y = float(self.station_table.item(row, 2).text())
        except Exception as e:
            return

        # Update Z using DEM lookup.
        new_z = self.get_elevation(x, y)
        self.station_table.blockSignals(True)
        self.station_table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{new_z:.2f}"))
        self.station_table.blockSignals(False)
        # Update stored station info.
        self.stations[sid]["coords"] = [x, y, new_z]
        # Update label on plotter: remove and add new label.
        self.plotter_widget.remove_actor(self.stations[sid]["actor"])
        new_marker = self.plotter_widget.add_point_labels([[x, y, new_z]], [f"Station {sid}"],
                                                           point_size=20, font_size=12)
        self.stations[sid]["actor"] = new_marker
        # Also update any train lines that include this station.
        self.update_all_lines()

    def delete_station(self):
        selected_ranges = self.station_table.selectedRanges()
        if not selected_ranges:
            QtWidgets.QMessageBox.warning(self, "Delete Station", "Select a station row to delete.")
            return
        row = selected_ranges[0].topRow()
        sid = int(self.station_table.item(row, 0).text())
        # Remove from table and dictionary.
        self.station_table.removeRow(row)
        if sid in self.stations:
            self.plotter_widget.remove_actor(self.stations[sid]["actor"])
            del self.stations[sid]
        # Remove station from any train lines that include it.
        to_remove = []
        for lid, line in self.train_lines.items():
            if sid in line["station_ids"]:
                line["station_ids"].remove(sid)
                if len(line["station_ids"]) < 2:
                    # Mark line for removal if fewer than 2 stations.
                    to_remove.append(lid)
                else:
                    self.update_line_actor(lid)
        for lid in to_remove:
            self.delete_line_by_id(lid)
        self.update_line_table()

    def add_line(self):
        if len(self.stations) < 2:
            QtWidgets.QMessageBox.warning(self, "Add Line", "At least two stations are needed to create a train line.")
            return
        # Open a dialog to let user select stations (by id).
        dialog = StationSelectionDialog(self.get_station_data(), self)
        if dialog.exec() == QtWidgets.QDialog.Rejected:
            return
        selected_ids = dialog.selected_ids
        if len(selected_ids) < 2:
            QtWidgets.QMessageBox.warning(self, "Add Line", "Select at least two stations.")
            return
        # Temporarily highlight the chosen stations.
        for sid in selected_ids:
            coords = self.stations[sid]["coords"]
            self.plotter_widget.add_mesh(pv.Sphere(radius=500, center=coords), color="yellow", name=f"hl_{sid}")
        # Create the spline using the order from the dialog.
        points = np.array([self.stations[sid]["coords"] for sid in selected_ids])
        spline = pv.Spline(points, 100)
        color = [random.random() for _ in range(3)]
        actor = self.plotter_widget.add_mesh(spline, color=color, line_width=4)
        lid = self.next_line_id
        self.next_line_id += 1
        self.train_lines[lid] = {"station_ids": selected_ids, "actor": actor, "color": color}
        self.update_line_table()
        # Remove temporary highlights.
        for sid in selected_ids:
            self.plotter_widget.remove_actor(f"hl_{sid}")

    def edit_line(self):
        # Edit a selected train line.
        selected_ranges = self.line_table.selectedRanges()
        if not selected_ranges:
            QtWidgets.QMessageBox.warning(self, "Edit Line", "Select a train line row to edit.")
            return
        row = selected_ranges[0].topRow()
        lid = int(self.line_table.item(row, 0).text())
        # Open dialog to select new station order.
        dialog = StationSelectionDialog(self.get_station_data(), self)
        # Pre-select current stations.
        for i in range(dialog.list_widget.count()):
            item = dialog.list_widget.item(i)
            if item.data(QtCore.Qt.UserRole) in self.train_lines[lid]["station_ids"]:
                item.setSelected(True)
        if dialog.exec() == QtWidgets.QDialog.Rejected:
            return
        new_station_ids = dialog.selected_ids
        if len(new_station_ids) < 2:
            QtWidgets.QMessageBox.warning(self, "Edit Line", "At least two stations are needed for a line.")
            return
        # Remove the old spline actor.
        self.plotter_widget.remove_actor(self.train_lines[lid]["actor"])
        # Create new spline.
        points = np.array([self.stations[sid]["coords"] for sid in new_station_ids])
        spline = pv.Spline(points, 100)
        color = self.train_lines[lid]["color"]
        actor = self.plotter_widget.add_mesh(spline, color=color, line_width=4)
        self.train_lines[lid]["station_ids"] = new_station_ids
        self.train_lines[lid]["actor"] = actor
        self.update_line_table()

    def delete_line(self):
        selected_ranges = self.line_table.selectedRanges()
        if not selected_ranges:
            QtWidgets.QMessageBox.warning(self, "Delete Line", "Select a train line row to delete.")
            return
        row = selected_ranges[0].topRow()
        lid = int(self.line_table.item(row, 0).text())
        self.delete_line_by_id(lid)

    def delete_line_by_id(self, lid):
        if lid in self.train_lines:
            self.plotter_widget.remove_actor(self.train_lines[lid]["actor"])
            del self.train_lines[lid]
            self.update_line_table()

    def update_line_actor(self, lid):
        # Recreate the spline actor for line lid based on current station coordinates.
        station_ids = self.train_lines[lid]["station_ids"]
        if len(station_ids) < 2:
            return
        points = np.array([self.stations[sid]["coords"] for sid in station_ids if sid in self.stations])
        self.plotter_widget.remove_actor(self.train_lines[lid]["actor"])
        spline = pv.Spline(points, 100)
        color = self.train_lines[lid]["color"]
        actor = self.plotter_widget.add_mesh(spline, color=color, line_width=4)
        self.train_lines[lid]["actor"] = actor

    def update_all_lines(self):
        for lid in self.train_lines.keys():
            self.update_line_actor(lid)

    def update_line_table(self):
        self.line_table.blockSignals(True)
        self.line_table.setRowCount(0)
        for lid, line in self.train_lines.items():
            row = self.line_table.rowCount()
            self.line_table.insertRow(row)
            item_id = QtWidgets.QTableWidgetItem(str(lid))
            item_id.setFlags(item_id.flags() & ~QtCore.Qt.ItemIsEditable)
            self.line_table.setItem(row, 0, item_id)
            station_str = ", ".join(str(sid) for sid in line["station_ids"])
            self.line_table.setItem(row, 1, QtWidgets.QTableWidgetItem(station_str))
        self.line_table.blockSignals(False)

    def line_cell_changed(self, row, column):
        # Allow editing the station id list in the line table.
        if column != 1:
            return
        try:
            lid = int(self.line_table.item(row, 0).text())
            text = self.line_table.item(row, 1).text()
            new_ids = [int(x.strip()) for x in text.split(",") if x.strip().isdigit()]
            if len(new_ids) < 2:
                QtWidgets.QMessageBox.warning(self, "Edit Line", "A line must have at least two stations.")
                self.update_line_table()
                return
            self.train_lines[lid]["station_ids"] = new_ids
            self.update_line_actor(lid)
        except Exception as e:
            print("Error editing line:", e)

    def get_station_data(self):
        # Return a dict of station_id -> (x,y,z) for use in dialogs.
        return {sid: tuple(data["coords"]) for sid, data in self.stations.items()}

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = TrainLineUI()
    window.show()
    sys.exit(app.exec())
