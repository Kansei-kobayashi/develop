from PySide6.QtWidgets import (
    QApplication, QDialog, QWidget, QVBoxLayout, QLabel, QPushButton,
    QFileDialog, QTabWidget, QCheckBox, QHBoxLayout, QDoubleSpinBox, QLineEdit,
    QRadioButton, QButtonGroup
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from maya import OpenMayaUI as omui
from shiboken6 import wrapInstance
import maya.cmds as cmds
import os
import subprocess


class SceneClassifier:
    def __init__(self):
        self.selected = cmds.ls(selection=True)
        self.geometry = []
        self.lights = []
        self.cameras = []

    def classify(self):
        default_cameras = {"persp", "top", "front", "side"}

        for t in self.selected:
            if cmds.nodeType(t) != "transform":
                continue
        
            shapes = cmds.listRelatives(t, shapes=True, path=True) or []
            if not shapes:
                continue
        
            shape = shapes[0]
            shape_type = cmds.nodeType(shape)
        
            if shape_type == 'mesh':
                self.geometry.append(t)
            elif 'light' in shape_type.lower():
                self.lights.append(t)
            elif shape_type == 'camera':
                cam_name = t.split('|')[-1] 
                if cam_name not in default_cameras:
                    self.cameras.append(t)

class USDExporter:
    def __init__(self, obj_name, output_dir):
        self.obj_name = obj_name
        self.output_dir = output_dir

    def export_geo(self, full_obj_path, frame_range=None):
        file_name = f"{self.obj_name}.usda"
        export_path = os.path.join(self.output_dir, file_name)
        cmds.select(full_obj_path, replace=True)
        cmds.mayaUSDExport(file=export_path, selection=True, shadingMode="none", frameRange=(frame_range[0], frame_range[1]))
        
        return export_path
        
    def export_light(self, full_obj_path, frame_range=None):
        file_name = f"{self.obj_name}.usda"
        export_path = os.path.join(self.output_dir, file_name)
        cmds.select(full_obj_path, replace=True)
        cmds.mayaUSDExport(file=export_path, selection=True, shadingMode="none", frameRange=(frame_range[0], frame_range[1]))

        print(f"# ライトは正常に書き出されました: {export_path}")
        return export_path

    def export_cam(self, full_obj_path, frame_range=None):
        file_name = f"{self.obj_name}.usda"
        export_path = os.path.join(self.output_dir, file_name)
        cmds.select(full_obj_path, replace=True)
        cmds.mayaUSDExport(file=export_path, selection=True, shadingMode="none", frameRange=(frame_range[0], frame_range[1]))

        print(f"# カメラは正常に書き出されました: {export_path}")
        return export_path




def write_combine_usd(
    file_info_list,
    output_dir,
    combine_filename="combine_geo.usda",
    root_name="Root",
    kind="geo",
    add_prim_path=False):
    lines = [
        '#usda 1.0',
        f'def Xform "{root_name}" {{'
    ]

    for name, path in file_info_list:
        rel_path = path if add_prim_path else os.path.basename(path)
        mtl_rel = f"{name}_mtl.usda" if kind == "geo" else ""

        lines.append(f'    def "{name}"')
        lines.append('    (')
        lines.append('        kind = "component"')
        lines.append('        prepend references = [')

        if add_prim_path:
            lines.append(f'            @./{rel_path}@</{name}>')
        else:
            lines.append(f'            @./{rel_path}@')

        lines.append('        ]')
        lines.append('    ) {}')

    lines.append('}')

    combine_path = os.path.join(output_dir, combine_filename)
    with open(combine_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    print(f"コンバインUSDは正常に書き出されました: {combine_path}")
    return combine_path

def write_houdini_loader_script(
    geo_combine_list,
    output_dir,
    script_name="create_loader.py",
    stage_path="/stage"):

    lines = [
        "import hou",
        "",
        "def create_loader():",
        f'    stage = hou.node("{stage_path}")',
        ""
    ]
    
    prev_node_var = None
    for i, (name, usd_path) in enumerate(geo_combine_list, start=1):
        node_var = f"node{i}"
        lines.append(f'    {node_var} = stage.createNode("sublayer", node_name="{name}_sublayer")')
        lines.append(f'    {node_var}.parm("filepath1").set("{output_dir}'+"/"+f'{usd_path}")')
        
        if prev_node_var is not None:
            lines.append(f'    {node_var}.setInput(0, {prev_node_var})')
        prev_node_var = node_var

    lines.append(f'    {prev_node_var}.setDisplayFlag(True)')
    lines.append("    stage.layoutChildren()")
    lines.append('create_loader()')

    script_path = os.path.join(output_dir, script_name)
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    print(f"Houdini loader script written to: {script_path}")




def execution(output_dir, export_houdini_py=False, frame_range=None):
    selected_groups = cmds.ls(selection=True, long=True, type="transform")
    if not selected_groups:
        cmds.warning("グループが選択されていません。")
        return

    geo_combine_list = []

    for group in selected_groups:
        group_name = group.split('|')[-1]

        descendants = cmds.listRelatives(group, allDescendents=True, fullPath=True) or []
        mesh_transforms = []
        for d in descendants:
            if cmds.nodeType(d) == "mesh":
                parent = cmds.listRelatives(d, parent=True, fullPath=True)[0]
                if parent not in mesh_transforms:
                    mesh_transforms.append(parent)

        if not mesh_transforms:
            print(f"[{group_name}] にメッシュが見つかりませんでした。スキップします。")
            continue

        group_output_dir = os.path.join(output_dir, group_name)
        os.makedirs(group_output_dir, exist_ok=True)

        # Write each mesh
        exported_files = []
        for mesh in mesh_transforms:
            mesh_name = mesh.split('|')[-1]
            exporter = USDExporter(mesh_name, group_output_dir)
            file_path = exporter.export_geo(mesh, frame_range=frame_range)
            # exporter.write_materialx_usd(mesh)
            exported_files.append((mesh_name, file_path))

        combine_name = f"{group_name}_combine.usda"
        write_combine_usd(exported_files, group_output_dir, combine_filename=combine_name, root_name=group_name)
        combine_path = f"{group_name}/{combine_name}" 
        geo_combine_list.append((group_name, combine_path))

    classifier_all = SceneClassifier()
    classifier_all.selected = cmds.ls(selection=True, type="transform")
    classifier_all.classify()

    # Light
    light_exported = []

    if classifier_all.lights:
        light_folder = os.path.join(output_dir, "Lights")
        os.makedirs(light_folder, exist_ok=True)
    
        for light in classifier_all.lights:
            light_name = light.split('|')[-1]
            exporter = USDExporter(light_name, light_folder)
            light_path = exporter.export_light(light, frame_range=frame_range)
            light_exported.append((light_name, light_path))
    
        if light_exported:
            rel_light_exported = []
            for name, abs_path in light_exported:
                rel_path = os.path.relpath(abs_path, output_dir).replace("\\", "/")
                rel_light_exported.append((name, rel_path))
    
            write_combine_usd(
                rel_light_exported,
                output_dir,
                combine_filename="combine_light.usda",
                root_name="Root",
                kind="light",
                add_prim_path=True
            )
    # Camera
    cam_exported = []
    
    if classifier_all.cameras:
        cam_folder = os.path.join(output_dir, "Cameras")
        os.makedirs(cam_folder, exist_ok=True)
    
        for cam in classifier_all.cameras:
            cam_name = cam.split('|')[-1]  
            exporter = USDExporter(cam_name, cam_folder)
            cam_path = exporter.export_cam(cam, frame_range=frame_range) 
            cam_exported.append((cam_name, cam_path))
    
        if cam_exported:
            rel_cam_exported = []
            for name, abs_path in cam_exported:
                rel_path = os.path.relpath(abs_path, output_dir).replace("\\", "/")
                rel_cam_exported.append((name, rel_path))
    
            write_combine_usd(
                rel_cam_exported,
                output_dir,
                combine_filename="combine_cam.usda",
                root_name="Root",
                kind="cam",
                add_prim_path=True
            )

    # All geo combine USD
    if geo_combine_list:
        write_combine_usd(
            geo_combine_list,
            output_dir,
            combine_filename="geo_combine.usda",
            root_name="Root",
            kind="scene",
            add_prim_path=True
        )
        
    # python  
    if geo_combine_list and export_houdini_py:
        write_houdini_loader_script(
            geo_combine_list,
            output_dir,
            script_name="houdini_loader.py",
            stage_path="/stage"
        )


class MaterialXExporter:
    def __init__(self):
        pass

    def get_assigned_material(self, obj):
        shapes = cmds.listRelatives(obj, shapes=True, fullPath=True) or []
        for shape in shapes:
            sg = cmds.listConnections(shape, type="shadingEngine")
            if sg:
                materials = cmds.ls(cmds.listConnections(sg), materials=True)
                if materials:
                    return materials
        return []

    def get_texture_path(self, material, attr):
        if attr == "normalCamera":
            normal_nodes = cmds.listConnections(f"{material}.{attr}", type="aiNormalMap") or []
            for normal_node in normal_nodes:
                file_nodes = cmds.listConnections(f"{normal_node}.input", type="file") or []
                for file_node in file_nodes:
                    return cmds.getAttr(f"{file_node}.fileTextureName")

            bump_nodes = cmds.listConnections(f"{material}.{attr}", type="bump2d") or []
            for bump_node in bump_nodes:
                file_nodes = cmds.listConnections(f"{bump_node}.bumpValue", type="file") or []
                for file_node in file_nodes:
                    return cmds.getAttr(f"{file_node}.fileTextureName")
        else:
            file_nodes = cmds.listConnections(f"{material}.{attr}", type="file") or []
            for file_node in file_nodes:
                return cmds.getAttr(f"{file_node}.fileTextureName")
        return None

    def get_input_value(self, material, attr, default):
        """デフォルト値と異なる値を返す（floatやcolor3）"""
        try:
            value = cmds.getAttr(f"{material}.{attr}")
            if isinstance(value, list):
                value = value[0] 
            if value != default:
                return value
        except:
            pass
        return None

    def write_materialx(self, obj, output_dir=None):
        material_list = self.get_assigned_material(obj)
        if not material_list:
            print(f"# Warning: マテリアルが割り当てられていません: {obj}")
            return None
    
        mat = material_list[0]
        shader_name = f"SR_{mat}"
        graph_name = f"NG_{mat}"
    
        base_color_path = self.get_texture_path(mat, "baseColor")
        roughness_path = self.get_texture_path(mat, "specularRoughness")
        metalness_path = self.get_texture_path(mat, "metalness")
        normal_path = self.get_texture_path(mat, "normalCamera")
        transmission_path = self.get_texture_path(mat, "transmission")
        coat_path = self.get_texture_path(mat, "coat")
    
        base_color_value = self.get_input_value(mat, "baseColor", (0.8, 0.8, 0.8))
        roughness_value = self.get_input_value(mat, "specularRoughness", 0.2)
        metalness_value = self.get_input_value(mat, "metalness", 0.0)
        transmission_value = self.get_input_value(mat, "transmission", 0.0)
        coat_value = self.get_input_value(mat, "coat", 0.0)
    
        lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<materialx version="1.38">',
            f'  <nodegraph name="{graph_name}">'
        ]
    
        if base_color_path:
            lines.append(f'    <image name="baseColor_tex" type="color3">')
            lines.append(f'      <input name="file" type="filename" value="{base_color_path}" />')
            lines.append(f'    </image>')
            lines.append(f'    <output name="base_color_output" type="color3" nodename="baseColor_tex" />')
        elif base_color_value:
            r, g, b = base_color_value
            lines.append(f'    <constant name="baseColor_val" type="color3">')
            lines.append(f'      <input name="value" type="color3" value="{r},{g},{b}" />')
            lines.append(f'    </constant>')
            lines.append(f'    <output name="base_color_output" type="color3" nodename="baseColor_val" />')
    
        if roughness_path:
            lines.append(f'    <image name="roughness_tex" type="float">')
            lines.append(f'      <input name="file" type="filename" value="{roughness_path}" />')
            lines.append(f'    </image>')
            lines.append(f'    <output name="roughness_output" type="float" nodename="roughness_tex" />')
        elif roughness_value is not None:
            lines.append(f'    <constant name="roughness_val" type="float">')
            lines.append(f'      <input name="value" type="float" value="{roughness_value}" />')
            lines.append(f'    </constant>')
            lines.append(f'    <output name="roughness_output" type="float" nodename="roughness_val" />')
    
        if metalness_path:
            lines.append(f'    <image name="metalness_tex" type="float">')
            lines.append(f'      <input name="file" type="filename" value="{metalness_path}" />')
            lines.append(f'    </image>')
            lines.append(f'    <output name="metalness_output" type="float" nodename="metalness_tex" />')
        elif metalness_value is not None:
            lines.append(f'    <constant name="metalness_val" type="float">')
            lines.append(f'      <input name="value" type="float" value="{metalness_value}" />')
            lines.append(f'    </constant>')
            lines.append(f'    <output name="metalness_output" type="float" nodename="metalness_val" />')

        if transmission_path:
            lines.append(f'    <image name="transmission_tex" type="float">')
            lines.append(f'      <input name="file" type="filename" value="{transmission_path}" />')
            lines.append(f'    </image>')
            lines.append(f'    <output name="transmission_output" type="float" nodename="transmission_tex" />')
        elif transmission_value is not None:
            lines.append(f'    <constant name="transmission_val" type="float">')
            lines.append(f'      <input name="value" type="float" value="{transmission_value}" />')
            lines.append(f'    </constant>')
            lines.append(f'    <output name="transmission_output" type="float" nodename="transmission_val" />')

        if coat_path:
            lines.append(f'    <image name="coat_tex" type="float">')
            lines.append(f'      <input name="file" type="filename" value="{coat_path}" />')
            lines.append(f'    </image>')
            lines.append(f'    <output name="coat_output" type="float" nodename="coat_tex" />')
        elif coat_value is not None:
            lines.append(f'    <constant name="coat_val" type="float">')
            lines.append(f'      <input name="value" type="float" value="{coat_value}" />')
            lines.append(f'    </constant>')
            lines.append(f'    <output name="coat_output" type="float" nodename="coat_val" />')
  
        if normal_path:
            lines.append(f'    <texcoord name="st" type="vector2" />')
            lines.append(f'    <image name="normal_tex" type="vector3" GLSLFX_usage="normal">')
            lines.append(f'      <input name="file" type="filename" value="{normal_path}" />')
            lines.append(f'      <input name="texcoord" type="vector2" nodename="st" />')
            lines.append(f'    </image>')
            lines.append(f'    <output name="normal_output" type="vector3" nodename="normal_tex" />')
    
        lines.append(f'  </nodegraph>')
        lines.append(f'  <standard_surface name="{shader_name}" type="surfaceshader">')
    
        if base_color_path or base_color_value:
            lines.append(f'    <input name="base_color" type="color3" output="base_color_output" nodegraph="{graph_name}" />')
        if roughness_path or roughness_value is not None:
            lines.append(f'    <input name="specular_roughness" type="float" output="roughness_output" nodegraph="{graph_name}" />')
        if metalness_path or metalness_value is not None:
            lines.append(f'    <input name="metalness" type="float" output="metalness_output" nodegraph="{graph_name}" />')
        if transmission_path or transmission_value is not None:
            lines.append(f'    <input name="transmission" type="float" output="transmission_output" nodegraph="{graph_name}" />')
        if coat_path or coat_value is not None:
            lines.append(f'    <input name="coat" type="float" output="coat_output" nodegraph="{graph_name}" />')
        if normal_path:
            lines.append(f'    <input name="normal" type="vector3" output="normal_output" nodegraph="{graph_name}" />')
    
        lines.append(f'  </standard_surface>')
        lines.append(f'  <surfacematerial name="{mat}" type="material">')
        lines.append(f'    <input name="surfaceshader" type="surfaceshader" nodename="{shader_name}" />')
        lines.append(f'  </surfacematerial>')
        lines.append('</materialx>')
    
        if output_dir:
            filepath = os.path.join(output_dir, f"{mat}.mtlx")
        else:
            first_path = base_color_path or roughness_path or metalness_path or normal_path
            outdir = os.path.dirname(first_path) if first_path else "C:/temp"
            filepath = os.path.join(outdir, f"{mat}.mtlx")
    
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            print(f"MaterialXを書き出しました: {filepath}")
        except Exception as e:
            print(f"# Error: 書き出しに失敗しました: {e}")
            return None
    
        return os.path.dirname(filepath)

def maya_main_window():
    return wrapInstance(int(omui.MQtUtil.mainWindow()), QWidget)

# USD Exporter tab
class USDExporterTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.output_dir = ""
        self.double2_values = [1.0, 1.0]
        self.init_ui()
        self.time_job   = cmds.scriptJob(event=["timeChanged", self.update_double_inputs], protected=True)
        self.render_job_start = cmds.scriptJob(attributeChange=["defaultRenderGlobals.startFrame", self.update_double_inputs],protected=True)
        self.render_job_end = cmds.scriptJob(attributeChange=["defaultRenderGlobals.endFrame", self.update_double_inputs],protected=True)
        self.slider_job = cmds.scriptJob(event=["playbackRangeChanged", self.update_double_inputs], protected=True)

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.folder_btn = QPushButton("書き出し先フォルダを選択")
        self.folder_btn.clicked.connect(self.select_folder)
        self.folder_label = QLabel("未選択")
        
        radio_layout = QVBoxLayout()
        self.radio_group = QButtonGroup(self)
        
        double_layout = QHBoxLayout()
        self.double_input1 = QLineEdit()
        self.double_input2 = QLineEdit()
    
        self.radio1 = QRadioButton("Current frame")
        self.radio2 = QRadioButton("Render setting")
        self.radio3 = QRadioButton("Time Slider")
        self.radio4 = QRadioButton("Start/End")
    
        self.radio3.setChecked(True)
    
        self.radio_group.addButton(self.radio1)
        self.radio_group.addButton(self.radio2)
        self.radio_group.addButton(self.radio3)
        self.radio_group.addButton(self.radio4)
    
        radio_layout.addWidget(QLabel("フレームレンジ"))
        radio_layout.addWidget(self.radio1)
        radio_layout.addWidget(self.radio2)
        radio_layout.addWidget(self.radio3)
        radio_layout.addWidget(self.radio4)

        self.radio1.toggled.connect(self.update_double_inputs)
        self.radio2.toggled.connect(self.update_double_inputs)
        self.radio3.toggled.connect(self.update_double_inputs)
        self.radio4.toggled.connect(self.update_double_inputs)

        self.update_double_inputs()
    
        validator = QDoubleValidator(-9999.0000, 9999.0000, 3)
        self.double_input1.setValidator(validator)
        self.double_input2.setValidator(validator)
    
        start_frame = cmds.playbackOptions(q=True, min=True)
        end_frame   = cmds.playbackOptions(q=True, max=True)
        
        self.double_input1.setText(f"{start_frame:.4f}")
        self.double_input2.setText(f"{end_frame:.4f}")
    
        double_layout.addWidget(QLabel("Start/End"))
        double_layout.addWidget(self.double_input1)
        double_layout.addWidget(self.double_input2)
        
        self.houdini_py_checkbox = QCheckBox("Houdini用Pythonを書き出す")
        self.houdini_py_checkbox.setChecked(False)

        self.export_btn = QPushButton("USDを書き出す")
        self.export_btn.clicked.connect(self.export_usd)

        layout.addLayout(radio_layout)
        layout.addLayout(double_layout)
        layout.addWidget(self.folder_btn)
        layout.addWidget(self.folder_label)
        layout.addWidget(self.houdini_py_checkbox)
        layout.addWidget(self.export_btn)

    def update_double_inputs(self):
        if self.radio1.isChecked():  # Current Frame
            current_frame = cmds.currentTime(q=True)
            self.double_input1.setText(f"{current_frame:.4f}")
            self.double_input2.setText(f"{current_frame:.4f}")
            self.double_input1.setEnabled(False)
            self.double_input2.setEnabled(False)
    
        elif self.radio3.isChecked():  # Time Slider
            start = cmds.playbackOptions(q=True, min=True)
            end = cmds.playbackOptions(q=True, max=True)
            self.double_input1.setText(f"{start:.4f}")
            self.double_input2.setText(f"{end:.4f}")
            self.double_input1.setEnabled(False)
            self.double_input2.setEnabled(False)
    
        elif self.radio2.isChecked():  # Render Settings
            start = cmds.getAttr("defaultRenderGlobals.startFrame")
            end = cmds.getAttr("defaultRenderGlobals.endFrame")
            self.double_input1.setText(f"{start:.4f}")
            self.double_input2.setText(f"{end:.4f}")
            self.double_input1.setEnabled(False)
            self.double_input2.setEnabled(False)
    
        else:  # Start/End
            self.double_input1.setEnabled(True)
            self.double_input2.setEnabled(True)
    
    def get_frame_range(self):
        start = float(self.double_input1.text())
        end = float(self.double_input2.text())
        return [start, end]


    def closeEvent(self, event):
        if hasattr(self, "slider_job") and cmds.scriptJob(exists=self.slider_job):
            cmds.scriptJob(kill=self.slider_job, force=True)
        super().closeEvent(event)
    
        
    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "書き出し先フォルダを選択")
        if folder:
            self.output_dir = folder
            self.folder_label.setText(folder)

    def export_usd(self):
        if not self.output_dir:
            cmds.warning("書き出し先フォルダを選択してください。")
            return
        classifier = SceneClassifier()
        classifier.classify()
        
        frame_range = self.get_frame_range()
        start_frame, end_frame = frame_range
        
        execution(self.output_dir, export_houdini_py=self.houdini_py_checkbox.isChecked(), frame_range=(start_frame, end_frame))

    def close_window(self):
        self.parent().parent().close()

# MaterialX Exporter tab
class MaterialXExporterTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.exporter = MaterialXExporter()
        self.output_dir = None
        self.setup_ui()
        self.manual_output_dir = None

    def setup_ui(self):
        layout = QVBoxLayout(self)

        self.export_button = QPushButton("MaterialXを書き出し")
        self.export_button.clicked.connect(self.export_materialx)

        self.open_folder_button = QPushButton("出力先フォルダを開く")
        self.open_folder_button.clicked.connect(self.open_output_folders)
        
        self.custom_output_checkbox = QCheckBox("出力先を手動で設定")
        self.custom_output_checkbox.stateChanged.connect(self.toggle_custom_output)
        
        self.select_output_button = QPushButton("書き出し先フォルダを選択")
        self.select_output_button.setEnabled(False)
        self.select_output_button.clicked.connect(self.select_output_folder)
        self.folder_label = QLabel("未選択")
         
        # Layout
        layout.addWidget(self.custom_output_checkbox)
        layout.addWidget(self.select_output_button)
        layout.addWidget(self.folder_label)
        layout.addWidget(self.export_button)
        layout.addWidget(self.open_folder_button)
               

    def export_materialx(self):
        exporter = MaterialXExporter()
        selection = cmds.ls(selection=True, long=True)
    
        if not selection:
            print("オブジェクトを選択してください。")
            return
    
        manual_dir = getattr(self, 'manual_output_dir', None) if self.custom_output_checkbox.isChecked() else None
    
        output_dirs = []
        for obj in selection:
            outdir = exporter.write_materialx(obj, manual_dir)
            if outdir:
                output_dirs.append(outdir)
        self.output_dirs = output_dirs

            
    def toggle_custom_output(self):
        if self.custom_output_checkbox.isChecked():
            self.select_output_button.setEnabled(True)
        else:
            self.select_output_button.setEnabled(False)


        
    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "出力先フォルダを選択")
        if folder:
            self.manual_output_dir = folder 
            self.folder_label.setText(folder)
            print(f"手動出力先フォルダ: {folder}")

    def open_output_folders(self):
        if hasattr(self, 'output_dirs') and self.output_dirs:
            for path in self.output_dirs:
                if os.path.exists(path):
                    if os.name == 'nt':
                        subprocess.Popen(["explorer", os.path.normpath(path)])
                    else:
                        subprocess.Popen(["xdg-open", path])
        else:
            print("出力先フォルダが設定されていません。")


    def close_window(self):
        self.parent().parent().close()

# GUI window
class ExporterMainWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or maya_main_window())
        self.setWindowTitle("USD / MaterialX Exporter")
        self.setMinimumWidth(470)
        self.setWindowFlags(Qt.Window)

        main_layout = QVBoxLayout(self)

        # Tabs
        self.tab_widget = QTabWidget()
        self.usd_tab = USDExporterTab()
        self.materialx_tab = MaterialXExporterTab()
        self.tab_widget.addTab(self.usd_tab, "USD Export")
        self.tab_widget.addTab(self.materialx_tab, "MaterialX Export")

        # Close button
        close_button = QPushButton("閉じる")
        close_button.clicked.connect(self.close)

        # Add to layout
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(close_button)


# Callback GUI
def show_exporter_gui():
    try:
        for widget in QApplication.allWidgets():
            if isinstance(widget, ExporterMainWindow):
                widget.close()
                widget.deleteLater()
    except Exception:
        pass

    win = ExporterMainWindow()
    win.show()
    
show_exporter_gui()