bl_info = {
    "name": "Audio Visualizer (Full Merge)",
    "author": "Hyacinthax + merged features",
    "version": (1, 0, 4),
    "blender": (4, 3, 0),
    "location": "View3D > Sidebar > Audio Visualizer",
    "description": "Visualize WAV or MP3 audio using animated geometry, primitives, and custom objects",
    "category": "Animation",
}

import bpy
import os
import wave
import numpy as np
from mathutils import Vector
import subprocess
import bmesh
from math import sin
import random

# ---------------- Core Visualizer ----------------
class BlenderVideoMaker:
    def __init__(self):
        self.wav_data = None
        self.sample_rate = None
        self.fft_data = None

    # ---------- Audio ----------
    def convert_mp3_to_wav(self, mp3_path):
        if not mp3_path or not os.path.exists(mp3_path):
            print("❌ Invalid MP3 path.")
            return None
        base, _ = os.path.splitext(mp3_path)
        wav_path = base + ".wav"

        ffmpeg_exe = "C:\\ffmpeg\\bin\\ffmpeg.exe"
        if not os.path.exists(ffmpeg_exe):
            print("❌ ffmpeg not found.")
            return None

        subprocess.run([ffmpeg_exe, "-y", "-i", mp3_path, wav_path],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return wav_path

    def load_audio(self, filepath):
        with wave.open(filepath, 'rb') as wf:
            data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
            if wf.getnchannels() == 2:
                data = data[::2]
            self.wav_data = data
            self.sample_rate = wf.getframerate()
        return self.wav_data, self.sample_rate

    def get_fft(self, frames_per_fft=2):
        if self.wav_data is None:
            print("⚠️ No audio loaded.")
            return

        fps = bpy.context.scene.render.fps
        duration_seconds = len(self.wav_data) / self.sample_rate
        total_frames = int(duration_seconds * fps)
        bpy.context.scene.frame_start = 1
        bpy.context.scene.frame_end = total_frames

        chunks = max(1, total_frames // frames_per_fft)
        chunk_size = len(self.wav_data) // chunks

        self.fft_data = np.array([
            np.mean(np.abs(np.fft.fft(self.wav_data[i*chunk_size:(i+1)*chunk_size])[:chunk_size//2]))
            for i in range(chunks)
        ])
        self.total_frames = total_frames
        print(f"✅ FFT computed ({chunks} chunks, {total_frames} frames)")

    # ---------- Scene ----------
    def clear_scene(self):
        for obj in [o for o in bpy.data.objects if o.type == 'MESH']:
            bpy.data.objects.remove(obj, do_unlink=True)

    def create_black_glass_floor(self, size=1000, depth=-3):
        mesh = bpy.data.meshes.new("BlackGlassFloor")
        floor = bpy.data.objects.new("BlackGlassFloor", mesh)
        bpy.context.collection.objects.link(floor)

        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1)
        bm.to_mesh(mesh)
        bm.free()

        floor.scale = (size, size, 1)
        floor.location.z = depth

        mat = bpy.data.materials.new(name="BlackGlass")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs['Base Color'].default_value = (0, 0, 0, 1)
            bsdf.inputs['Metallic'].default_value = 1.0
            bsdf.inputs['Roughness'].default_value = 0.05
        floor.data.materials.append(mat)
        print("✅ Black glass floor created.")

    # ---------- Wave objects ----------
    def create_wave_objects(self, count_x=10, count_y=10, spacing=0.5, settings=None):
        objs = []
        mat = self.create_material(settings.color, settings.material_type)

        for y in range(count_y):
            for x in range(count_x):
                loc = Vector((x*spacing, y*spacing, 0))

                # Custom object
                if settings.custom_object:
                    obj = settings.custom_object.copy()
                    if settings.use_linked_mesh:
                        obj.data = settings.custom_object.data
                    else:
                        obj.data = settings.custom_object.data.copy()
                    bpy.context.collection.objects.link(obj)
                    obj.location = loc
                else:  # Primitive fallback
                    if settings.mesh_type == 'CUBE':
                        bpy.ops.mesh.primitive_cube_add(size=0.3, location=loc)
                    elif settings.mesh_type == 'UV_SPHERE':
                        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.2, location=loc)
                    elif settings.mesh_type == 'ICO_SPHERE':
                        bpy.ops.mesh.primitive_ico_sphere_add(radius=0.2, location=loc)
                    elif settings.mesh_type == 'CYLINDER':
                        bpy.ops.mesh.primitive_cylinder_add(radius=0.15, depth=0.3, location=loc)
                    elif settings.mesh_type == 'CONE':
                        bpy.ops.mesh.primitive_cone_add(radius1=0.2, depth=0.4, location=loc)
                    elif settings.mesh_type == 'TORUS':
                        bpy.ops.mesh.primitive_torus_add(location=loc)
                    elif settings.mesh_type == 'PLANE':
                        bpy.ops.mesh.primitive_plane_add(size=0.4, location=loc)
                    obj = bpy.context.object

                # Apply material
                if obj.type == 'MESH' and not (settings.keep_original_materials and settings.custom_object):
                    if obj.data.materials:
                        obj.data.materials[0] = mat
                    else:
                        obj.data.materials.append(mat)

                objs.append(obj)
        return objs

    # ---------- Animate ----------
    def animate_objects(self, objs, exaggeration=2.5, morph_amount=0.12, z_wave_emphasis=0.15, animation_type='WAVE'):
        if self.fft_data is None:
            print("⚠️ FFT data missing.")
            return

        total_frames = getattr(self, "total_frames", 250)
        max_val = max(self.fft_data)
        base_positions = [obj.location.copy() for obj in objs]
        random_phases = [random.random() * np.pi * 2 for _ in objs]
        frames_per_chunk = max(1, total_frames // len(self.fft_data))
        frame = 1

        # Determine grid dimensions if needed for ROLL
        num_objs = len(objs)
        cols = int(np.sqrt(num_objs))  # assume roughly square grid
        rows = int(np.ceil(num_objs / cols))

        for chunk_i, amp in enumerate(self.fft_data):
            norm_amp = amp / max_val
            for i, obj in enumerate(objs):
                base = base_positions[i]
                phase = random_phases[i]
                t = frame * 0.05 + phase

                if animation_type == 'ROLL':
                    morph_x = morph_amount * sin(t)
                    morph_y = morph_amount * sin(t)
                    z_wave = norm_amp * exaggeration + z_wave_emphasis * sin(t)

                elif animation_type == 'MOUTH':
                    morph_x = morph_amount * sin(t + i * 0.1)
                    morph_y = morph_amount * sin(t * 1.1 + i * 0.1)
                    z_wave = norm_amp * exaggeration * sin(i * 0.2) + z_wave_emphasis * sin(t * 0.3)

                elif animation_type == 'WAVE':
                    # compute row/col index for wave roll
                    row = i // cols
                    col = i % cols
                    offset = (row + col) * 0.15  # stagger based on position

                    morph_x = morph_amount * sin(t + offset)
                    morph_y = morph_amount * sin(t + offset)
                    z_wave = norm_amp * exaggeration * sin(offset + t) + z_wave_emphasis * sin(t * 0.3)

                obj.location.x = base.x + morph_x
                obj.location.y = base.y + morph_y
                obj.location.z = base.z + z_wave
                obj.keyframe_insert(data_path="location", frame=frame)
            frame += frames_per_chunk

        print(f"✅ Animation complete ({animation_type} style, {frame} frames).")

    # ---------- Camera ----------
    def setup_camera(self, count_x=10, count_y=10, spacing=0.5):
        cam = next((c for c in bpy.data.objects if c.type=='CAMERA'), None)
        if not cam:
            bpy.ops.object.camera_add()
            cam = bpy.context.object
        cam.location = ((count_x-1)*spacing/2, (count_y-1)*spacing/2, max(count_x,count_y))
        cam.rotation_euler = (1.2,0,0)
        bpy.context.scene.camera = cam

    # ---------- Material ----------
    def create_material(self, color, material_type):
        mat = bpy.data.materials.new(name="VisualizerMaterial")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (*color,1)
            if material_type=='METALLIC': bsdf.inputs['Metallic'].default_value=1.0; bsdf.inputs['Roughness'].default_value=0.2
            elif material_type=='SHINY': bsdf.inputs['Roughness'].default_value=0.1
            elif material_type=='GLASS': bsdf.inputs['Transmission'].default_value=1.0; bsdf.inputs['Roughness'].default_value=0.0
            elif material_type=='ROUGH': bsdf.inputs['Roughness'].default_value=0.9
            elif material_type=='SMOOTH': bsdf.inputs['Roughness'].default_value=0.4
        return mat

# ---------------- Properties ----------------
class AVProperties(bpy.types.PropertyGroup):
    mp3_path: bpy.props.StringProperty(name="MP3 Path", subtype='FILE_PATH')

    # Wave pool
    rows: bpy.props.IntProperty(name="Rows", default=10, min=1)
    cols: bpy.props.IntProperty(name="Columns", default=10, min=1)
    spacing: bpy.props.FloatProperty(name="Spacing", default=0.5, min=0.01)

    # Floor
    floor_size: bpy.props.FloatProperty(name="Floor Size", default=1000, min=10)
    floor_depth: bpy.props.FloatProperty(name="Floor Depth", default=-10, min=-200)

    # Animation
    exaggeration: bpy.props.FloatProperty(name="Z Exaggeration", default=2.5, min=0.1, max=10)
    morph_amount: bpy.props.FloatProperty(name="Morph Amount", default=0.12, min=0.0, max=1.0)
    z_wave_emphasis: bpy.props.FloatProperty(name="Z Wave Emphasis", default=0.15, min=0.0, max=1.0)
    animation_type: bpy.props.EnumProperty(
        name="Animation Type",
        description="Choose animation style",
        items=[
            ('MOUTH', "Mouth", "All objects move together"),
            ('WAVE', "Wave", "Original wave animation"),
            ('ROLL', "Roll", "Wave rolls through the objects")
        ],
        default='WAVE'
    )


    # Objects & materials
    mesh_type: bpy.props.EnumProperty(
        name="Primitive",
        items=[('CUBE','Cube',''),('UV_SPHERE','UV Sphere',''),('ICO_SPHERE','Ico Sphere',''),
               ('CYLINDER','Cylinder',''),('CONE','Cone',''),('TORUS','Torus',''),('PLANE','Plane','')],
        default='ICO_SPHERE'
    )
    material_type: bpy.props.EnumProperty(
        name="Material",
        items=[('METALLIC','Metallic',''),('SHINY','Shiny',''),('GLASS','Glass',''),
               ('ROUGH','Rough',''),('SMOOTH','Smooth','')],
        default='SHINY'
    )
    color: bpy.props.FloatVectorProperty(name="Color", subtype='COLOR', size=3, default=(0.2,0.6,1.0))
    custom_object: bpy.props.PointerProperty(name="Custom Object", type=bpy.types.Object)
    use_linked_mesh: bpy.props.BoolProperty(name="Linked Mesh Data", default=False)
    keep_original_materials: bpy.props.BoolProperty(name="Keep Original Materials", default=False)
    use_geometry_nodes: bpy.props.BoolProperty(name="Use Geometry Nodes (Experimental)", default=False)

# ---------------- Operator ----------------
class AV_OT_ConvertAndVisualize(bpy.types.Operator):
    bl_idname = "av.convert_and_visualize"
    bl_label = "Convert + Visualize"

    def execute(self, context):
        props = context.scene.av_props
        maker = BlenderVideoMaker()

        if props.use_geometry_nodes:
            print("⚠️ Geometry Nodes backend not set up yet. Enable later in the code.")
            # TODO: GN setup here
            # Early return or fallback
            # return {'CANCELLED'}

        wav_path = maker.convert_mp3_to_wav(props.mp3_path)
        if not wav_path or not os.path.exists(wav_path):
            self.report({'ERROR'}, "Conversion failed or ffmpeg not found.")
            return {'CANCELLED'}

        maker.load_audio(wav_path)
        maker.get_fft()
        maker.clear_scene()
        maker.create_black_glass_floor(size=props.floor_size, depth=props.floor_depth)

        objs = maker.create_wave_objects(count_x=props.cols, count_y=props.rows, spacing=props.spacing, settings=props)
        maker.setup_camera(count_x=props.cols, count_y=props.rows, spacing=props.spacing)
        maker.animate_objects(
            objs,
            exaggeration=props.exaggeration,
            morph_amount=props.morph_amount,
            z_wave_emphasis=props.z_wave_emphasis,
            animation_type=props.animation_type
        )


        self.report({'INFO'}, f"✅ Visualization created from {os.path.basename(wav_path)}")
        return {'FINISHED'}

# ---------------- Panel ----------------
class AV_PT_MainPanel(bpy.types.Panel):
    bl_label = "Audio Visualizer"
    bl_idname = "AV_PT_MainPanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Audio Visualizer"

    def draw(self, context):
        layout = self.layout
        props = context.scene.av_props

        layout.prop(props, "mp3_path")

        layout.label(text="Grid Settings:")
        layout.prop(props, "rows")
        layout.prop(props, "cols")
        layout.prop(props, "spacing")

        layout.label(text="Floor Settings:")
        layout.prop(props, "floor_size")
        layout.prop(props, "floor_depth")

        layout.label(text="Animation Settings:")
        layout.prop(props, "exaggeration")
        layout.prop(props, "morph_amount")
        layout.prop(props, "z_wave_emphasis")
        layout.label(text="Animation Type:")
        layout.prop(props, "animation_type", expand=True)

        layout.label(text="Object / Material Settings:")
        layout.prop(props, "custom_object")
        layout.prop(props, "mesh_type")
        layout.prop(props, "use_linked_mesh")
        layout.prop(props, "keep_original_materials")
        layout.prop(props, "material_type")
        layout.prop(props, "color")

        layout.label(text="Advanced:")
        layout.prop(props, "use_geometry_nodes")

        # Keep this Last
        layout.operator("av.convert_and_visualize", icon="MOD_WAVE")

# ---------------- Register ----------------
classes = [AVProperties, AV_OT_ConvertAndVisualize, AV_PT_MainPanel]

def register():
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.Scene.av_props = bpy.props.PointerProperty(type=AVProperties)

def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
    del bpy.types.Scene.av_props

if __name__=="__main__":
    register()
