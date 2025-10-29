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

    def get_fft(self, chunks=200):
        import numpy as np
        if self.wav_data is None: return
        chunk_size = len(self.wav_data) // chunks
        self.fft_data = np.array([
            np.mean(np.abs(np.fft.fft(self.wav_data[i*chunk_size:(i+1)*chunk_size])[:chunk_size//2]))
            for i in range(chunks)
        ])
        print(f"✅ Computed FFT ({chunks} chunks).")

    # ---------- Scene ----------
    def clear_scene(self):
        import bpy
        for obj in [o for o in bpy.data.objects if o.type == 'MESH']:
            bpy.data.objects.remove(obj, do_unlink=True)

    def create_wave_objects(self, rows=100, cols=100, spacing=0.5):
        import bpy
        objs = []
        for y in range(rows):
            for x in range(cols):
                bpy.ops.mesh.primitive_ico_sphere_add(radius=0.2, location=(x*spacing, y*spacing, 0))
                objs.append(bpy.context.object)
        return objs

    def animate_objects(self, objs, rows=100, cols=100):
        import bpy
        from math import sin
        from mathutils import Vector
        if self.fft_data is None: return

        frame = 1
        max_val = max(self.fft_data)
        for amp in self.fft_data:
            for i, obj in enumerate(objs):
                x, y = i % cols, i // cols
                ripple = sin(x + y + frame/5)
                scale_factor = 1 + (amp/max_val) * ripple
                obj.scale = Vector((scale_factor, scale_factor, scale_factor))
                obj.keyframe_insert(data_path="scale", frame=frame)
            frame += 2
        print(f"✅ Animation complete ({frame} frames).")

    def setup_camera(self, rows=10, cols=10, spacing=0.5):
        import bpy
        # Use existing camera or create new
        cam = next((c for c in bpy.data.objects if c.type == 'CAMERA'), None)
        if not cam:
            bpy.ops.object.camera_add()
            cam = bpy.context.object

        # Position camera above the center
        cam.location = ((cols-1)*spacing/2, (rows-1)*spacing/2, max(rows, cols))
        cam.rotation_euler = (1.2, 0, 0)  # angled down
        bpy.context.scene.camera = cam

# ---------- Blender UI / Add-on ----------
# ---------- Blender UI / Add-on ----------
class AVProperties(bpy.types.PropertyGroup):
    mp3_path: bpy.props.StringProperty(name="MP3 Path", subtype='FILE_PATH')

    # Wave pool settings
    rows: bpy.props.IntProperty(name="Rows", default=100, min=1)
    cols: bpy.props.IntProperty(name="Columns", default=100, min=1)
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
