# Blender Video Maker
import bpy
import os
import ffmpeg
import wave
import numpy as np
from mathutils import Vector


class BlenderVideoMaker:
    def __init__(self, directory="."):
        self.directory = directory
        self.wav_data = None
        self.sample_rate = None
        self.fft_data = None

    # ---------- SYSTEM HELPERS ----------
    def clear_console(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def list_directory_path(self):
        os.system('dir' if os.name == 'nt' else 'ls')

    # ---------- AUDIO PROCESSING ----------
    def convert_mp3_to_wav(self, mp3_path, wav_path):
        """Converts an MP3 file to WAV using ffmpeg."""
        try:
            print(f"Converting {mp3_path} → {wav_path} ...")
            ffmpeg.input(mp3_path).output(wav_path).run(overwrite_output=True, quiet=True)
            print("✅ Conversion complete.")
        except Exception as e:
            print(f"❌ Error converting file: {e}")

    def list_wav_files(self):
        """List all .wav files in the working directory."""
        files = [f for f in os.listdir(self.directory) if f.lower().endswith(".wav")]
        if not files:
            print("❌ No WAV files found.")
            return []
        print("🎵 Available WAV files:")
        for i, f in enumerate(files, start=1):
            print(f"{i}. {f}")
        return files

    def load_audio(self, filepath):
        """Reads WAV file and returns numpy array + framerate."""
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
        """Compute FFT averages over segments of the audio."""
        if self.wav_data is None or self.sample_rate is None:
            print("⚠️ Load an audio file first.")
            return None
        data = self.wav_data
        sample_rate = self.sample_rate
        chunk_size = len(data) // chunks
        fft_bands = []
        for i in range(chunks):
            segment = data[i*chunk_size:(i+1)*chunk_size]
            fft_vals = np.abs(np.fft.fft(segment))[:chunk_size//2]
            fft_bands.append(np.mean(fft_vals))
        self.fft_data = np.array(fft_bands)
        print(f"✅ Computed FFT ({chunks} chunks).")
        return self.fft_data

    # ---------- BLENDER OBJECTS ----------
    def create_wave_objects(self, count=50):
        """Create a line of icospheres in Blender."""
        objs = []
        for i in range(count):
            bpy.ops.mesh.primitive_ico_sphere_add(radius=0.2, location=(i*0.3, 0, 0))
            objs.append(bpy.context.object)
        return objs

    def animate_objects(self, objs):
        """Animate scale of objects based on FFT data."""
        if self.fft_data is None:
            print("⚠️ Compute FFT first.")
            return
        frame = 1
        max_val = max(self.fft_data)
        for amp in self.fft_data:
            for i, obj in enumerate(objs):
                scale_factor = 1 + (amp / max_val) * np.sin(i)
                obj.scale = Vector((scale_factor, scale_factor, scale_factor))
                obj.keyframe_insert(data_path="scale", frame=frame)
            frame += 2
        print(f"✅ Animation complete ({frame} frames total).")

    def clear_scene(self):
        """Deletes all objects in the Blender scene."""
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        print("🧹 Cleared existing scene objects.")

    # ---------- RUNNERS ----------
    def run(self):
        """Interactive WAV visualizer runner inside Blender."""
        self.clear_console()
        print("=== 🎧 WAV Visualizer Runner ===\n")
        files = self.list_wav_files()
        if not files:
            return

        try:
            choice = int(input("\nSelect a file number: ")) - 1
            filepath = os.path.join(self.directory, files[choice])
        except (ValueError, IndexError):
            print("❌ Invalid selection.")
            return

        print(f"\n▶ Loading: {filepath}")
        self.load_audio(filepath)
        self.get_fft(chunks=200)

        self.clear_scene()
        objs = self.create_wave_objects(count=50)
        self.animate_objects(objs)
        print("\n✅ Done! Animation keyframes inserted.")

    def main_menu(self):
        """Text-based main menu for managing conversions and visualizations."""
        while True:
            print("\n🎵 AUDIO VISUALIZER MENU 🎵")
            print("1️⃣  Convert MP3 → WAV")
            print("2️⃣  Read WAV file")
            print("3️⃣  Generate FFT data")
            print("4️⃣  Run Blender animation")
            print("5️⃣  Exit")
            choice = input("Select an option: ")

            if choice == "1":
                mp3 = input("Enter MP3 file path: ").strip('"')
                wav = input("Enter desired WAV output path: ").strip('"')
                self.convert_mp3_to_wav(mp3, wav)

            elif choice == "2":
                path = input("Enter WAV file path: ").strip('"')
                self.load_audio(path)

            elif choice == "3":
                self.get_fft()

            elif choice == "4":
                self.run()

            elif choice == "5":
                print("👋 Exiting program.")
                break

            else:
                print("❌ Invalid option. Please select 1-5.")


# ---------- Example Usage ----------
# In Blender's scripting editor:
# from blender_video_maker import BlenderVideoMaker
# visualizer = BlenderVideoMaker(directory="C:/path/to/wav/folder")
# visualizer.main_menu()
