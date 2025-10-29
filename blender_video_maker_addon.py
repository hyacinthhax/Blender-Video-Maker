bl_info = {
    "name": "Audio Visualizer",
    "author": "Hyacinthax",
    "version": (1, 0, 2),
    "blender": (4, 3, 0),
    "location": "View3D > Sidebar > Audio Visualizer",
    "description": "Visualize WAV or MP3 audio using animated geometry",
    "category": "Animation",
}

import bpy
import os
import wave
import numpy as np
from mathutils import Vector
import subprocess
import shutil


# ---------- Core visualizer logic ----------
class BlenderVideoMaker:
    def __init__(self):
        self.wav_data = None
        self.sample_rate = None
        self.fft_data = None

    # ---------- Audio ----------
    def convert_mp3_to_wav(self, mp3_path):
        import subprocess, os
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
        import wave, numpy as np
        with wave.open(filepath, 'rb') as wf:
            data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
            if wf.getnchannels() == 2:
                data = data[::2]
            self.wav_data = data
            self.sample_rate = wf.getframerate()
        return self.wav_data, self.sample_rate

    def get_fft(self, frames_per_fft=2):
        import numpy as np
        if self.wav_data is None:
            return

        import bpy
        fps = bpy.context.scene.render.fps
        duration_seconds = len(self.wav_data) / self.sample_rate
        total_frames = int(duration_seconds * fps)

        # Set scene frame range to match the song length
        bpy.context.scene.frame_start = 1
        bpy.context.scene.frame_end = total_frames

        # Calculate number of chunks based on frames_per_fft
        chunks = max(1, total_frames // frames_per_fft)
        chunk_size = len(self.wav_data) // chunks

        self.fft_data = np.array([
            np.mean(np.abs(np.fft.fft(self.wav_data[i*chunk_size:(i+1)*chunk_size])[:chunk_size//2]))
            for i in range(chunks)
        ])

        # Store total_frames for animate_objects
        self.total_frames = total_frames

        print(f"✅ Computed FFT ({chunks} chunks, {total_frames} frames)")


    # ---------- Scene ----------
    def clear_scene(self):
        import bpy
        for obj in [o for o in bpy.data.objects if o.type == 'MESH']:
            bpy.data.objects.remove(obj, do_unlink=True)

    def create_black_glass_floor(self, size=1000, depth=-50):
        import bpy

        # Create plane
        mesh = bpy.data.meshes.new("BlackGlassFloor")
        floor = bpy.data.objects.new("BlackGlassFloor", mesh)
        bpy.context.collection.objects.link(floor)
        
        # Make it huge
        floor.scale = (size, size, 1)
        floor.location.z = depth

        # Create black glass material
        mat = bpy.data.materials.new(name="BlackGlass")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs['Base Color'].default_value = (0, 0, 0, 1)  # black
            bsdf.inputs['Metallic'].default_value = 1.0
            bsdf.inputs['Roughness'].default_value = 0.0
        floor.data.materials.append(mat)

        print("✅ Black glass floor created.")


    def create_wave_objects(self, rows=10, cols=10, spacing=0.5):
        import bpy
        import bmesh

        objs = []

        for y in range(rows):
            for x in range(cols):
                # Create mesh object
                mesh = bpy.data.meshes.new(f"Ico_{x}_{y}")
                obj = bpy.data.objects.new(f"Ico_{x}_{y}", mesh)
                bpy.context.collection.objects.link(obj)

                # Build icosphere
                bm = bmesh.new()
                bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.2)
                bm.to_mesh(mesh)
                bm.free()

                # Position in grid
                obj.location.x = x * spacing
                obj.location.y = y * spacing
                obj.location.z = 0

                objs.append(obj)

        return objs


    def animate_objects(self, objs, rows=20, cols=20):
        import bpy
        import numpy as np
        from math import sin
        import random

        if self.fft_data is None or self.wav_data is None or self.sample_rate is None:
            print("⚠️ FFT or audio data not computed.")
            return

        total_frames = getattr(self, "total_frames", 250)
        max_val = max(self.fft_data)
        exaggeration = 2.5   # z motion scale (reduced for smoother wave)
        morph_amount = 0.12  # random lateral morph
        z_wave_emphasis = 0.15  # small offset in z for existing wave emphasis

        # Store original base positions so grid stays fixed
        base_positions = [obj.location.copy() for obj in objs]

        # Random phase per object so morphs differ
        random_phases = [random.random() * np.pi * 2 for _ in objs]

        frames_per_chunk = max(1, total_frames // len(self.fft_data))
        frame = 1

        for chunk_i, amp in enumerate(self.fft_data):
            norm_amp = amp / max_val

            for i, obj in enumerate(objs):
                base = base_positions[i]
                phase = random_phases[i]

                # Random morph direction changes slowly over time
                t = frame * 0.05 + phase
                morph_x = morph_amount * sin(t + random.uniform(-1, 1))
                morph_y = morph_amount * sin(t * 1.1 + random.uniform(-1, 1))

                # Z-axis follows the audio, small extra wave emphasis
                z_wave = norm_amp * exaggeration * sin(i * 0.2) + z_wave_emphasis * sin(t * 0.3)

                # Apply displacements relative to base position
                obj.location.x = base.x + morph_x
                obj.location.y = base.y + morph_y
                obj.location.z = base.z + z_wave

                obj.keyframe_insert(data_path="location", frame=frame)

            frame += frames_per_chunk

        print(f"✅ Animation complete ({frame} frames, grid preserved).")


    def setup_camera(self, rows=10, cols=10, spacing=0.5):
        import bpy

        # Use existing camera or create a new one if none exists
        cam = next((c for c in bpy.data.objects if c.type == 'CAMERA'), None)
        if not cam:
            bpy.ops.object.camera_add()
            cam = bpy.context.object

        # ✅ Your custom camera position and rotation
        cam.location = (5, -4.2, 0)
        cam.rotation_euler = (np.radians(90), np.radians(0), np.radians(-0))

        # Make sure the scene uses this camera
        bpy.context.scene.camera = cam

        print("📸 Camera set to position (5, -4.2, 0) with rotation (90°, 0°, 0°).")


# ---------- Blender UI / Add-on ----------
class AVProperties(bpy.types.PropertyGroup):
    mp3_path: bpy.props.StringProperty(name="MP3 Path", subtype='FILE_PATH')

    # Wave pool settings
    rows: bpy.props.IntProperty(name="Rows", default=20, min=1)
    cols: bpy.props.IntProperty(name="Columns", default=20, min=1)
    spacing: bpy.props.FloatProperty(name="Spacing", default=0.5, min=0.01)

class AV_OT_ConvertAndVisualize(bpy.types.Operator):
    bl_idname = "av.convert_and_visualize"
    bl_label = "Convert + Visualize"
    bl_description = "Convert MP3 to WAV and run the visualizer"

    def execute(self, context):
        props = context.scene.av_props
        maker = BlenderVideoMaker()

        # Convert MP3 to WAV
        wav_path = maker.convert_mp3_to_wav(props.mp3_path)
        if not wav_path or not os.path.exists(wav_path):
            self.report({'ERROR'}, "Conversion failed or ffmpeg not found.")
            return {'CANCELLED'}

        # Load audio and compute FFT
        maker.load_audio(wav_path)
        maker.get_fft()

        # Clear previous objects
        maker.clear_scene()

        maker.create_black_glass_floor()

        # Create 2D wave pool
        objs = maker.create_wave_objects(rows=props.rows, cols=props.cols, spacing=props.spacing)

        # Set up camera separately
        maker.setup_camera()

        # Animate objects
        maker.animate_objects(objs, rows=props.rows, cols=props.cols)

        self.report({'INFO'}, f"Visualization created from {os.path.basename(wav_path)}")
        return {'FINISHED'}

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
        layout.prop(props, "rows")
        layout.prop(props, "cols")
        layout.prop(props, "spacing")
        layout.operator("av.convert_and_visualize", icon="MOD_WAVE")



classes = [AVProperties, AV_OT_ConvertAndVisualize, AV_PT_MainPanel]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.av_props = bpy.props.PointerProperty(type=AVProperties)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.av_props


if __name__ == "__main__":
    register()
