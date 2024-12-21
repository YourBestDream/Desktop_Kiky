import sys
from PyQt5 import QtCore, QtGui, QtWidgets

class DesktopSprite(QtWidgets.QWidget):
    def __init__(self, sprite_path):
        super().__init__()
        
        # Remove window decorations and ensure the sprite stays on top
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint |
                            QtCore.Qt.WindowStaysOnTopHint |
                            QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # Load the sprite and size the widget accordingly
        self.sprite = QtGui.QPixmap(sprite_path)
        self.resize(self.sprite.size())

        # Current position and velocity
        self.current_x = 0
        self.current_y = 0
        self.velocity_x = 0
        self.velocity_y = 0

        # Tweak these parameters to adjust speed, “stickiness,” and parallax
        self.accel = 0.03      # how strongly the sprite accelerates toward the cursor
        self.friction = 0.75    # how quickly the sprite slows down
        self.parallax_factor = 0.15  # extra offset based on velocity for a parallax feel

        # Update timer (roughly 60 FPS)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_sprite_position)
        self.timer.start(16)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.drawPixmap(0, 0, self.sprite)

    def update_sprite_position(self):
        # Get the current cursor position
        cursor_pos = QtGui.QCursor.pos()

        # We want the sprite to be on the left of the cursor
        target_x = cursor_pos.x() - self.width()
        target_y = cursor_pos.y() - self.height() // 2

        # Calculate the difference from the sprite's current position to the target
        dx = target_x - self.current_x
        dy = target_y - self.current_y

        # Accelerate the sprite towards the target
        self.velocity_x += dx * self.accel
        self.velocity_y += dy * self.accel

        # Apply friction to slow down
        self.velocity_x *= self.friction
        self.velocity_y *= self.friction

        # Update the sprite’s current position
        self.current_x += self.velocity_x - 1
        self.current_y += self.velocity_y

        # Add a little parallax offset (dependent on velocity)
        parallax_x = self.velocity_x * self.parallax_factor
        parallax_y = self.velocity_y * self.parallax_factor

        # Compute final position
        final_x = self.current_x + parallax_x
        final_y = self.current_y + parallax_y

        # Move the sprite
        self.move(int(final_x), int(final_y))


def main():
    app = QtWidgets.QApplication(sys.argv)
    desktop_sprite = DesktopSprite("image.png")
    desktop_sprite.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
