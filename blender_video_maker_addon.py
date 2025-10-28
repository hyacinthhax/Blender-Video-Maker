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

    def convert_mp3_to_wav(self, mp3_path):
        if not mp3_path or not os.path.exists(mp3_path):
            print("❌ Invalid MP3 path.")
            return None

        base, _ = os.path.splitext(mp3_path)
        wav_path = base + ".wav"

        # Ensure ffmpeg exists
        ffmpeg_exe = shutil.which("ffmpeg")
        if not ffmpeg_exe:
            print("❌ ffmpeg not found in PATH.")
            return None

        print(f"🎶 Converting {mp3_path} → {wav_path}")
        result = subprocess.run(
            [ffmpeg_exe, "-y", "-i", mp3_path, wav_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:
            print("❌ Conversion failed:")
            print(result.stderr)
            return None

        print("✅ Conversion complete.")
        return wav_path

    def load_audio(self, filepath):
        with wave.open(filepath, 'rb') as wf:
            n_channels = wf.getnchannels()
            n_frames = wf.getnframes()
            framerate = wf.getframerate()
            raw_data = wf.readframes(n_frames)
            data = np.frombuffer(raw_data, dtype=np.int16)
            if n_channels == 2:
                data = data[::2]
            self.wav_data = data
            self.sample_rate = framerate
            return data, framerate

    def get_fft(self, chunks=200):
        if self.wav_data is None:
            print("⚠️ Load audio first.")
            return
        data = self.wav_data
        chunk_size = len(data) // chunks
        fft_bands = []
        for i in range(chunks):
            seg = data[i * chunk_size:(i + 1) * chunk_size]
            fft_vals = np.abs(np.fft.fft(seg))[:chunk_size // 2]
            fft_bands.append(np.mean(fft_vals))
        self.fft_data = np.array(fft_bands)
        print(f"✅ Computed FFT ({chunks} chunks).")

    def clear_scene(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        print("🧹 Scene cleared.")

    def create_wave_objects(self, count=50):
        objs = []
        for i in range(count):
            bpy.ops.mesh.primitive_ico_sphere_add(radius=0.2, location=(i * 0.3, 0, 0))
            objs.append(bpy.context.object)
        return objs

    def animate_objects(self, objs):
        if self.fft_data is None:
            print("⚠️ FFT not computed.")
            return
        frame = 1
        max_val = max(self.fft_data)
        for amp in self.fft_data:
            for i, obj in enumerate(objs):
                scale_factor = 1 + (amp / max_val) * np.sin(i)
                obj.scale = Vector((scale_factor,) * 3)
                obj.keyframe_insert(data_path="scale", frame=frame)
            frame += 2
        print(f"✅ Animation complete ({frame} frames).")


# ---------- Blender UI / Add-on ----------
class AVProperties(bpy.types.PropertyGroup):
    mp3_path: bpy.props.StringProperty(name="MP3 Path", subtype='FILE_PATH')


class AV_OT_ConvertAndVisualize(bpy.types.Operator):
    bl_idname = "av.convert_and_visualize"
    bl_label = "Convert + Visualize"
    bl_description = "Convert MP3 to WAV and run the visualizer"

    def execute(self, context):
        props = context.scene.av_props
        maker = BlenderVideoMaker()

        wav_path = maker.convert_mp3_to_wav(props.mp3_path)
        if not wav_path or not os.path.exists(wav_path):
            self.report({'ERROR'}, "Conversion failed or ffmpeg not found.")
            return {'CANCELLED'}

        maker.load_audio(wav_path)
        maker.get_fft()
        maker.clear_scene()
        objs = maker.create_wave_objects()
        maker.animate_objects(objs)
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
