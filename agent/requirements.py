import subprocess
import sys

def install_requirements():
    print("Installing Antigravity PC Agent dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("\n[Success] All dependencies installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"\n[Error] Failed to install dependencies: {e}")
        sys.exit(1)

if __name__ == "__main__":
    install_requirements()
