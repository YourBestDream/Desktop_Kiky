import sys
import math
from PyQt5 import QtCore, QtGui, QtWidgets

class DesktopSprite(QtWidgets.QWidget):
    def __init__(self, sprite_path, paw_path):
        super().__init__()

        # Window setup
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint |
                            QtCore.Qt.WindowStaysOnTopHint |
                            QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # Main sprite
        self.sprite = QtGui.QPixmap(sprite_path)
        self.resize(self.sprite.size())

        # Paw trace sprite
        self.paw_pixmap = QtGui.QPixmap(paw_path)
        self.paw_traces = []  # will hold info about each paw trace

        # Current position and velocity
        self.current_x = 0
        self.current_y = 0
        self.velocity_x = 0
        self.velocity_y = 0

        # Movement parameters
        self.accel = 0.03         # how strongly the sprite accelerates toward the cursor
        self.friction = 0.75      # how quickly the sprite slows down
        self.parallax_factor = 0.15  # extra offset based on velocity for a parallax feel

        # Paw fading time (milliseconds)
        self.fade_time = 2000

        # Update timer (roughly 60 FPS)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_sprite_position)
        self.timer.start(16)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)

        # Draw each paw trace behind the main sprite
        now = QtCore.QTime.currentTime()
        for paw in list(self.paw_traces):
            elapsed = paw['birth_time'].msecsTo(now)
            if elapsed > self.fade_time:
                # Remove old paw traces
                self.paw_traces.remove(paw)
                continue

            # Calculate opacity (fade from 255 down to 0)
            alpha = 255 - int(255 * elapsed / self.fade_time)
            painter.save()
            painter.setOpacity(alpha / 255.0)

            # Position and rotate so the paw faces the direction we were moving
            painter.translate(paw['x'], paw['y'])
            painter.rotate(paw['angle'])
            # Draw centered
            painter.drawPixmap(-self.paw_pixmap.width()//2,
                               -self.paw_pixmap.height()//2,
                               self.paw_pixmap)
            painter.restore()

        # Finally, draw the main sprite on top
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

        # Calculate a parallax offset (dependent on velocity)
        parallax_x = self.velocity_x * self.parallax_factor
        parallax_y = self.velocity_y * self.parallax_factor

        # Compute final position
        final_x = self.current_x + parallax_x
        final_y = self.current_y + parallax_y

        # Move the sprite
        self.move(int(final_x), int(final_y))

        # Create a new paw trace each update (optional: you could do this conditionally)
        # Compute rotation based on velocity angle
        angle = math.degrees(math.atan2(self.velocity_y, self.velocity_x)) if self.velocity_x or self.velocity_y else 0
        self.paw_traces.append({
            'x': final_x + self.width()//2,
            'y': final_y + self.height()//2,
            'angle': angle,
            'birth_time': QtCore.QTime.currentTime()
        })

        # Force a redraw
        self.update()


def main():
    app = QtWidgets.QApplication(sys.argv)
    # Provide the paths to your main sprite and the paws sprite
    desktop_sprite = DesktopSprite("image.png", "paws.png")
    desktop_sprite.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
