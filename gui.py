import random
import numpy as np

from PySide6 import QtWidgets, QtGui, QtCore
from pyvistaqt import QtInteractor

import dem_utils
import station_utils
import line_utils
import io  # I/O functions for saving and importing

def rgb_to_hex(rgb):
    r, g, b = rgb
    return f"#{int(r*255):02X}{int(g*255):02X}{int(b*255):02X}"

def hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip('#')
    if len(hex_str) != 6:
        return [0,1,0]
    r = int(hex_str[0:2], 16)/255.0
    g = int(hex_str[2:4], 16)/255.0
    b = int(hex_str[4:6], 16)/255.0
    return [r, g, b]

class LineEditorDialog(QtWidgets.QDialog):
    """
    A dialog for editing (or creating) a line.
    Provides two list widgets so the user can select and order stations,
    plus fields to change the line name and color.
    """
    def __init__(self, available_stations, current_line=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Line")
        self.resize(500, 400)
        self.selected_color = None

        layout = QtWidgets.QVBoxLayout(self)

        # Line name field
        name_layout = QtWidgets.QHBoxLayout()
        name_label = QtWidgets.QLabel("Line Name:")
        self.name_edit = QtWidgets.QLineEdit()
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)

        # Color selection
        color_layout = QtWidgets.QHBoxLayout()
        color_label = QtWidgets.QLabel("Line Color:")
        self.color_button = QtWidgets.QPushButton("Select Color")
        self.color_button.clicked.connect(self.choose_color)
        color_layout.addWidget(color_label)
        color_layout.addWidget(self.color_button)
        layout.addLayout(color_layout)

        # Two-list widget for available and selected stations
        lists_layout = QtWidgets.QHBoxLayout()
        available_layout = QtWidgets.QVBoxLayout()
        available_layout.addWidget(QtWidgets.QLabel("Available Stations"))
        self.available_list = QtWidgets.QListWidget()
        self.available_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        available_layout.addWidget(self.available_list)
        lists_layout.addLayout(available_layout)

        control_layout = QtWidgets.QVBoxLayout()
        self.btn_add = QtWidgets.QPushButton(">>")
        self.btn_remove = QtWidgets.QPushButton("<<")
        self.btn_add.clicked.connect(self.move_selected_to_selected)
        self.btn_remove.clicked.connect(self.move_selected_to_available)
        control_layout.addWidget(self.btn_add)
        control_layout.addWidget(self.btn_remove)
        control_layout.addStretch()
        lists_layout.addLayout(control_layout)

        selected_layout = QtWidgets.QVBoxLayout()
        selected_layout.addWidget(QtWidgets.QLabel("Selected Stations"))
        self.selected_list = QtWidgets.QListWidget()
        self.selected_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        self.selected_list.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        selected_layout.addWidget(self.selected_list)
        lists_layout.addLayout(selected_layout)

        layout.addLayout(lists_layout)

        # OK/Cancel buttons
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        # Populate available stations
        self.available_list.addItems(available_stations)

        # If editing an existing line, pre-populate fields and lists
        if current_line:
            self.name_edit.setText(current_line.get("name", ""))
            self.selected_color = current_line.get("color", [0,1,0])
            self.color_button.setStyleSheet("background-color: %s" % rgb_to_hex(self.selected_color))
            current_stations = current_line.get("station_ids", [])
            for st in current_stations:
                items = self.available_list.findItems(st, QtCore.Qt.MatchExactly)
                for item in items:
                    row = self.available_list.row(item)
                    self.available_list.takeItem(row)
                self.selected_list.addItem(st)
        else:
            self.selected_color = [random.random() for _ in range(3)]
            self.color_button.setStyleSheet("background-color: %s" % rgb_to_hex(self.selected_color))
            self.name_edit.setText("")

    def move_selected_to_selected(self):
        for item in self.available_list.selectedItems():
            self.available_list.takeItem(self.available_list.row(item))
            self.selected_list.addItem(item.text())

    def move_selected_to_available(self):
        for item in self.selected_list.selectedItems():
            self.selected_list.takeItem(self.selected_list.row(item))
            self.available_list.addItem(item.text())

    def choose_color(self):
        color = QtWidgets.QColorDialog.getColor()
        if color.isValid():
            self.selected_color = [color.red()/255.0, color.green()/255.0, color.blue()/255.0]
            self.color_button.setStyleSheet("background-color: %s" % color.name())

    def get_line_data(self):
        line_name = self.name_edit.text().strip()
        selected_stations = []
        for i in range(self.selected_list.count()):
            selected_stations.append(self.selected_list.item(i).text())
        return {"name": line_name, "station_ids": selected_stations, "color": self.selected_color}

class TrainLineUI(QtWidgets.QMainWindow):
    """
    Main window with embedded PyVista plotter and QTableWidgets for stations and lines.
    Contains buttons for editing lines (including reordering and selecting stations),
    Save/Import functionality, and actions to clear all and load a new DEM.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Train Line Editor")
        self.resize(1600, 900)

        # Data structures:
        self.stations = {}  # key = station_id (int), value = {"name": str, "coords": [x,y,z], "actor": label_actor}
        self.next_station_id = 1

        self.lines = {}     # key = line_id (int), value = {"name": str, "station_ids": [station names],
                              # "actor": line_actor, "color": [r,g,b]}
        self.next_line_id = 1

        # Set up main layout
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QHBoxLayout(central_widget)

        # PyVista plotter widget
        self.plotter_widget = QtInteractor(self)
        main_layout.addWidget(self.plotter_widget.interactor, stretch=3)

        # Right panel with tables and buttons
        control_panel = QtWidgets.QFrame()
        control_panel.setFixedWidth(400)
        cp_layout = QtWidgets.QVBoxLayout(control_panel)
        main_layout.addWidget(control_panel, stretch=1)

        # Station Table
        cp_layout.addWidget(QtWidgets.QLabel("Stations (Name, X, Y, Z):"))
        self.station_table = QtWidgets.QTableWidget(0, 4)
        self.station_table.setHorizontalHeaderLabels(["Name", "X", "Y", "Z"])
        self.station_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        cp_layout.addWidget(self.station_table)

        # Buttons for stations
        station_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_add_station = QtWidgets.QPushButton("Add Station (Click Plot)")
        self.btn_del_station = QtWidgets.QPushButton("Delete Station")
        station_btn_layout.addWidget(self.btn_add_station)
        station_btn_layout.addWidget(self.btn_del_station)
        cp_layout.addLayout(station_btn_layout)

        # Line Table with 3 columns: Line Name, Station IDs, Color
        cp_layout.addWidget(QtWidgets.QLabel("Lines (Line Name, Station IDs, Color):"))
        self.line_table = QtWidgets.QTableWidget(0, 3)
        self.line_table.setHorizontalHeaderLabels(["Line Name", "Station IDs", "Color"])
        self.line_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        cp_layout.addWidget(self.line_table)

        # Buttons for lines
        line_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_add_line = QtWidgets.QPushButton("Add Line")
        self.btn_edit_line = QtWidgets.QPushButton("Edit Line")
        self.btn_del_line = QtWidgets.QPushButton("Delete Line")
        line_btn_layout.addWidget(self.btn_add_line)
        line_btn_layout.addWidget(self.btn_edit_line)
        line_btn_layout.addWidget(self.btn_del_line)
        cp_layout.addLayout(line_btn_layout)

        # Save and Import Buttons
        io_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_save = QtWidgets.QPushButton("Save")
        self.btn_import = QtWidgets.QPushButton("Import")
        io_btn_layout.addWidget(self.btn_save)
        io_btn_layout.addWidget(self.btn_import)
        cp_layout.addLayout(io_btn_layout)

        cp_layout.addStretch()

        # Connect signals
        self.btn_add_station.clicked.connect(self.instruct_add_station)
        self.btn_del_station.clicked.connect(self.delete_station)
        self.btn_add_line.clicked.connect(self.add_line)
        self.btn_edit_line.clicked.connect(self.edit_line)
        self.btn_del_line.clicked.connect(self.delete_line)
        self.btn_save.clicked.connect(self.save_data)
        self.btn_import.clicked.connect(self.import_data)
        self.station_table.cellChanged.connect(self.station_table_cell_changed)
        self.line_table.cellChanged.connect(self.line_table_cell_changed)

        # DEM setup
        self.dem_data = None
        self.x_coords = None
        self.y_coords = None
        self.setup_dem()

        # Enable point picking (using revised callback signature)
        self.plotter_widget.enable_point_picking(callback=self.point_picked, use_picker=True)

        # Create menubar with File and View menus
        self.create_menus()

    # ---------------------
    # Menu / View actions
    # ---------------------
    def create_menus(self):
        menubar = self.menuBar()

        # File menu with "Load DEM" and "Clear All" actions.
        file_menu = menubar.addMenu("File")

        load_dem_action = QtGui.QAction("Load DEM", self)
        load_dem_action.triggered.connect(self.load_new_dem)
        file_menu.addAction(load_dem_action)

        clear_all_action = QtGui.QAction("Clear All", self)
        clear_all_action.triggered.connect(self.clear_all)
        file_menu.addAction(clear_all_action)

        # View menu
        view_menu = menubar.addMenu("View")

        toggle_grid_action = QtGui.QAction("Toggle Grid", self)
        toggle_grid_action.setCheckable(True)
        toggle_grid_action.setChecked(True)
        toggle_grid_action.triggered.connect(self.toggle_grid)
        view_menu.addAction(toggle_grid_action)

        reset_camera_action = QtGui.QAction("Reset Camera", self)
        reset_camera_action.triggered.connect(self.reset_camera)
        view_menu.addAction(reset_camera_action)

        top_view_action = QtGui.QAction("Top View (XY)", self)
        top_view_action.triggered.connect(self.view_xy_plane)
        view_menu.addAction(top_view_action)

    def load_new_dem(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load DEM", "", "TIFF Files (*.tif *.tiff)")
        if filename:
            try:
                data = dem_utils.visual_to_elevation(filename)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", str(e))
                return
            boundaries = (0, 0, 100000, 100000)
            land, sea, self.x_coords, self.y_coords, self.dem_data = dem_utils.plot_dem_in_pyvista(data, boundaries)
            self.plotter_widget.clear()  # clear existing meshes
            self.plotter_widget.add_mesh(land, show_edges=False, cmap="binary")
            self.plotter_widget.add_mesh(sea, show_edges=False, color="navy")
            self.plotter_widget.show_grid()
            self.plotter_widget.reset_camera()
            # After a new DEM is loaded, refresh station markers to update their Z values.
            self.refresh_stations_on_plot()
            self.refresh_lines_on_plot()

    def clear_all(self):
        # Clear stations and lines from tables and plotter
        self.station_table.setRowCount(0)
        self.line_table.setRowCount(0)
        for st_data in self.stations.values():
            self.plotter_widget.remove_actor(st_data["actor"])
        self.stations.clear()
        for line_data in self.lines.values():
            self.plotter_widget.remove_actor(line_data["actor"])
        self.lines.clear()
        self.next_station_id = 1
        self.next_line_id = 1

    def toggle_grid(self, checked):
        if checked:
            self.plotter_widget.show_grid()
        else:
            self.plotter_widget.hide_grid()

    def reset_camera(self):
        self.plotter_widget.reset_camera()

    def view_xy_plane(self):
        self.plotter_widget.view_xy()

    # ---------------------
    # DEM / Elevation
    # ---------------------
    def setup_dem(self):
        boundaries = (0, 0, 100000, 100000)
        try:
            data = dem_utils.visual_to_elevation("gradient_map.tiff")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))
            return
        land, sea, self.x_coords, self.y_coords, self.dem_data = dem_utils.plot_dem_in_pyvista(data, boundaries)
        self.plotter_widget.add_mesh(land, show_edges=False, cmap="binary")
        self.plotter_widget.add_mesh(sea, show_edges=False, color="navy")
        self.plotter_widget.show_grid()
        self.plotter_widget.reset_camera()

    def get_elevation(self, x, y):
        if self.dem_data is None:
            return 0
        i = np.abs(self.x_coords - x).argmin()
        j = np.abs(self.y_coords - y).argmin()
        return self.dem_data[i, j]

    # ---------------------
    # Stations
    # ---------------------
    def instruct_add_station(self):
        QtWidgets.QMessageBox.information(self, "Add Station", "Click on the plot to add a station.")

    def point_picked(self, point, p):
        if point is None:
            return
        x, y = point[0], point[1]
        z = self.get_elevation(x, y)
        name = f"Station {self.next_station_id}"
        self.next_station_id += 1

        row = self.station_table.rowCount()
        self.station_table.insertRow(row)
        self.station_table.setItem(row, 0, QtWidgets.QTableWidgetItem(name))
        self.station_table.setItem(row, 1, QtWidgets.QTableWidgetItem(f"{x:.2f}"))
        self.station_table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{y:.2f}"))
        self.station_table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{z:.2f}"))

        self.refresh_stations_on_plot()
        self.refresh_lines_on_plot()

    def station_table_cell_changed(self, row, column):
        item_x = self.station_table.item(row, 1)
        item_y = self.station_table.item(row, 2)
        if item_x is None or item_y is None:
            return
        if column in [1, 2]:
            try:
                x = float(item_x.text())
                y = float(item_y.text())
            except ValueError:
                return
            z = self.get_elevation(x, y)
            self.station_table.blockSignals(True)
            self.station_table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{z:.2f}"))
            self.station_table.blockSignals(False)
        self.refresh_stations_on_plot()
        self.refresh_lines_on_plot()

    def delete_station(self):
        selected_ranges = self.station_table.selectedRanges()
        if not selected_ranges:
            QtWidgets.QMessageBox.warning(self, "Delete Station", "Select a station row to delete.")
            return
        row = selected_ranges[0].topRow()
        self.station_table.removeRow(row)
        self.refresh_stations_on_plot()
        self.refresh_lines_on_plot()

    def refresh_stations_on_plot(self):
        for st_data in self.stations.values():
            self.plotter_widget.remove_actor(st_data["actor"])
        self.stations.clear()

        row_count = self.station_table.rowCount()
        station_id_counter = 1
        for row in range(row_count):
            name_item = self.station_table.item(row, 0)
            x_item = self.station_table.item(row, 1)
            y_item = self.station_table.item(row, 2)
            z_item = self.station_table.item(row, 3)
            if not (name_item and x_item and y_item and z_item):
                continue
            st_name = name_item.text()
            try:
                x = float(x_item.text())
                y = float(y_item.text())
                z = float(z_item.text())
            except ValueError:
                continue
            coords = [x, y, z]
            label_actor = self.plotter_widget.add_point_labels([coords], [st_name], point_size=20, font_size=12)
            self.stations[station_id_counter] = {"name": st_name, "coords": coords, "actor": label_actor}
            station_id_counter += 1

    # ---------------------
    # Lines
    # ---------------------
    def line_table_cell_changed(self, row, column):
        self.refresh_lines_on_plot()

    def add_line(self):
        if len(self.stations) < 2:
            QtWidgets.QMessageBox.warning(self, "Add Line", "Need at least two stations.")
            return
        available_stations = [st_data["name"] for st_data in self.stations.values()]
        dlg = LineEditorDialog(available_stations, None, self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            new_line = dlg.get_line_data()
            row = self.line_table.rowCount()
            self.line_table.insertRow(row)
            self.line_table.setItem(row, 0, QtWidgets.QTableWidgetItem(new_line["name"]))
            self.line_table.setItem(row, 1, QtWidgets.QTableWidgetItem(", ".join(new_line["station_ids"])))
            self.line_table.setItem(row, 2, QtWidgets.QTableWidgetItem(rgb_to_hex(new_line["color"])))
            self.refresh_lines_on_plot()

    def edit_line(self):
        selected_ranges = self.line_table.selectedRanges()
        if not selected_ranges:
            QtWidgets.QMessageBox.warning(self, "Edit Line", "Select a line row to edit.")
            return
        row = selected_ranges[0].topRow()
        name_item = self.line_table.item(row, 0)
        stations_item = self.line_table.item(row, 1)
        color_item = self.line_table.item(row, 2)
        if not (name_item and stations_item and color_item):
            return
        current_line = {
            "name": name_item.text().strip(),
            "station_ids": [s.strip() for s in stations_item.text().split(",") if s.strip()],
            "color": hex_to_rgb(color_item.text().strip())
        }
        available_stations = [st_data["name"] for st_data in self.stations.values()]
        dlg = LineEditorDialog(available_stations, current_line, self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            new_data = dlg.get_line_data()
            self.line_table.blockSignals(True)
            self.line_table.setItem(row, 0, QtWidgets.QTableWidgetItem(new_data["name"]))
            self.line_table.setItem(row, 1, QtWidgets.QTableWidgetItem(", ".join(new_data["station_ids"])))
            self.line_table.setItem(row, 2, QtWidgets.QTableWidgetItem(rgb_to_hex(new_data["color"])))
            self.line_table.blockSignals(False)
            self.refresh_lines_on_plot()

    def delete_line(self):
        selected_ranges = self.line_table.selectedRanges()
        if not selected_ranges:
            QtWidgets.QMessageBox.warning(self, "Delete Line", "Select a line row to delete.")
            return
        row = selected_ranges[0].topRow()
        self.line_table.removeRow(row)
        self.refresh_lines_on_plot()

    def refresh_lines_on_plot(self):
        for line_data in self.lines.values():
            self.plotter_widget.remove_actor(line_data["actor"])
        self.lines.clear()

        row_count = self.line_table.rowCount()
        line_id_counter = 1
        for row in range(row_count):
            name_item = self.line_table.item(row, 0)
            stations_item = self.line_table.item(row, 1)
            color_item = self.line_table.item(row, 2)
            if not (name_item and stations_item and color_item):
                continue
            line_name = name_item.text().strip()
            station_names_str = stations_item.text().strip()
            if not line_name or not station_names_str:
                continue
            st_names = [s.strip() for s in station_names_str.split(",") if s.strip()]
            coords = station_utils.lookup_station_coords(st_names, self.stations)
            if len(coords) < 2:
                continue
            color = hex_to_rgb(color_item.text().strip())
            actor = line_utils.build_line_actor(coords, self.plotter_widget, color=color)
            self.lines[line_id_counter] = {"name": line_name, "station_ids": st_names, "actor": actor, "color": color}
            line_id_counter += 1

    # ---------------------
    # I/O: Save and Import
    # ---------------------
    def save_data(self):
        station_data = []
        for row in range(self.station_table.rowCount()):
            name = self.station_table.item(row, 0).text() if self.station_table.item(row, 0) else ""
            x = self.station_table.item(row, 1).text() if self.station_table.item(row, 1) else ""
            y = self.station_table.item(row, 2).text() if self.station_table.item(row, 2) else ""
            z = self.station_table.item(row, 3).text() if self.station_table.item(row, 3) else ""
            station_data.append({"Name": name, "X": x, "Y": y, "Z": z})
        line_data = []
        for row in range(self.line_table.rowCount()):
            name = self.line_table.item(row, 0).text() if self.line_table.item(row, 0) else ""
            stations = self.line_table.item(row, 1).text() if self.line_table.item(row, 1) else ""
            color = self.line_table.item(row, 2).text() if self.line_table.item(row, 2) else ""
            line_data.append({"Line Name": name, "Stations": stations, "Color": color})
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Data", "", "HDF5 Files (*.h5)")
        if filename:
            try:
                io.save_data(station_data, line_data, filename)
                QtWidgets.QMessageBox.information(self, "Save Data", "Data saved successfully.")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Save Data Error", str(e))

    def import_data(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import Data", "", "HDF5 Files (*.h5)")
        if filename:
            try:
                station_data, line_data = io.import_data(filename)
                self.load_station_data(station_data)
                self.load_line_data(line_data)
                self.refresh_stations_on_plot()
                self.refresh_lines_on_plot()
                QtWidgets.QMessageBox.information(self, "Import Data", "Data imported successfully.")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Import Data Error", str(e))

    def load_station_data(self, station_data):
        self.station_table.setRowCount(0)
        for rec in station_data:
            row = self.station_table.rowCount()
            self.station_table.insertRow(row)
            self.station_table.setItem(row, 0, QtWidgets.QTableWidgetItem(rec.get("Name", "")))
            self.station_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(rec.get("X", ""))))
            self.station_table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(rec.get("Y", ""))))
            self.station_table.setItem(row, 3, QtWidgets.QTableWidgetItem(str(rec.get("Z", ""))))
        self.next_station_id = self.station_table.rowCount() + 1

    def load_line_data(self, line_data):
        self.line_table.setRowCount(0)
        for rec in line_data:
            row = self.line_table.rowCount()
            self.line_table.insertRow(row)
            self.line_table.setItem(row, 0, QtWidgets.QTableWidgetItem(rec.get("Line Name", "")))
            self.line_table.setItem(row, 1, QtWidgets.QTableWidgetItem(rec.get("Stations", "")))
            self.line_table.setItem(row, 2, QtWidgets.QTableWidgetItem(rec.get("Color", "#00FF00")))
        self.next_line_id = self.line_table.rowCount() + 1
