import sys
import math
from PyQt5 import QtCore, QtGui, QtWidgets

class DesktopSprite(QtWidgets.QWidget):
    def __init__(self, sprite_path, paw_path):
        super().__init__()

        # 1) Make a top-level, borderless, transparent overlay
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint |
                            QtCore.Qt.WindowStaysOnTopHint |
                            QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # 2) Resize to fill the entire screen
        screen_geo = QtWidgets.QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geo)

        # Main sprite
        self.sprite = QtGui.QPixmap(sprite_path)
        if self.sprite.isNull():
            print(f"ERROR: Sprite image '{sprite_path}' failed to load.")
        else:
            print(f"Sprite loaded: {sprite_path} with size {self.sprite.width()}x{self.sprite.height()}")
        self.sprite_x = 0
        self.sprite_y = 0

        # Paw trace sprite
        self.paw_pixmap = QtGui.QPixmap(paw_path)
        if self.paw_pixmap.isNull():
            print(f"ERROR: Paw image '{paw_path}' failed to load.")
        else:
            print(f"Paw loaded: {paw_path} with size {self.paw_pixmap.width()}x{self.paw_pixmap.height()}")
        self.paw_traces = []  # Each trace: {x, y, angle, birth_time}

        # Movement parameters
        self.accel = 0.03
        self.friction = 0.75
        self.parallax_factor = 0.15

        # Paw fading time and interval
        self.fade_time = 2000
        self.paw_interval = 500  # Milliseconds
        self.last_paw_time = QtCore.QTime.currentTime().addMSecs(-self.paw_interval)

        # Velocity
        self.vx = 0
        self.vy = 0

        # Timer ~60 FPS
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_sprite_position)
        self.timer.start(16)

        # Initially shape the window so only the sprite area is non-click-through
        self.updateWindowMask()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        now = QtCore.QTime.currentTime()

        # Draw the main sprite first with partial transparency
        painter.save()
        sprite_opacity = 0.5
        painter.setOpacity(sprite_opacity)
        painter.drawPixmap(int(self.sprite_x), int(self.sprite_y), self.sprite)
        painter.restore()

        # Draw paw traces on top of the sprite
        for paw in list(self.paw_traces):
            elapsed = paw['birth_time'].msecsTo(now)
            if elapsed > self.fade_time:
                self.paw_traces.remove(paw)
                print(f"DEBUG: Paw at x={paw['x']}, y={paw['y']} has faded.")
                continue

            alpha = 255 - int(255 * elapsed / self.fade_time)
            painter.save()
            painter.setOpacity(alpha / 255.0)
            painter.translate(paw['x'], paw['y'])
            painter.rotate(paw['angle'])
            painter.drawPixmap(-self.paw_pixmap.width() // 2,
                               -self.paw_pixmap.height() // 2,
                               self.paw_pixmap)
            painter.restore()

    def update_sprite_position(self):
        # Cursor position in global coordinates
        cursor_pos = QtGui.QCursor.pos()

        # Target position for the sprite
        target_x = cursor_pos.x() - self.sprite.width()
        target_y = cursor_pos.y() - self.sprite.height() // 2

        # Movement deltas
        dx = target_x - self.sprite_x
        dy = target_y - self.sprite_y

        # Accelerate and apply friction
        self.vx += dx * self.accel
        self.vy += dy * self.accel
        self.vx *= self.friction
        self.vy *= self.friction

        # Clamp velocities so the sprite fully stops
        if abs(self.vx) < 0.05:
            self.vx = 0
        if abs(self.vy) < 0.05:
            self.vy = 0

        # Update sprite position
        self.sprite_x += self.vx - 1
        self.sprite_y += self.vy

        # Parallax
        self.sprite_x += self.vx * self.parallax_factor
        self.sprite_y += self.vy * self.parallax_factor

        # Add a paw trace at intervals only if moving
        if abs(self.vx) > 0.1 or abs(self.vy) > 0.1:
            now = QtCore.QTime.currentTime()
            if self.last_paw_time.msecsTo(now) >= self.paw_interval:
                angle = math.degrees(math.atan2(self.vy, self.vx))
                center_x = self.sprite_x + self.sprite.width() // 2
                center_y = self.sprite_y + self.sprite.height() // 2

                # Debug print for paw coordinates
                print(f"DEBUG: Paw added at x={center_x}, y={center_y}, angle={angle}")

                self.paw_traces.append({
                    'x': center_x,
                    'y': center_y,
                    'angle': angle,
                    'birth_time': now
                })
                self.last_paw_time = now

        # Update window mask and redraw
        self.updateWindowMask()
        self.update()

    def updateWindowMask(self):
        """
        Sets the clickable region to just the bounding rectangle of the sprite
        plus bounding rectangles of paw traces.
        (If you still see no paws, comment out the setMask call entirely.)
        """
        mask_region = QtGui.QRegion()

        # Use bounding rectangle for sprite (avoid sprite.mask())
        if not self.sprite.isNull():
            sprite_rect = QtCore.QRect(
                int(self.sprite_x), 
                int(self.sprite_y), 
                self.sprite.width(), 
                self.sprite.height()
            )
            sprite_region = QtGui.QRegion(sprite_rect)
            mask_region = mask_region.united(sprite_region)

        # Use bounding rectangle for each paw
        for paw in self.paw_traces:
            paw_rect = QtCore.QRect(
                int(paw['x'] - self.paw_pixmap.width() // 2),
                int(paw['y'] - self.paw_pixmap.height() // 2),
                self.paw_pixmap.width(),
                self.paw_pixmap.height()
            )
            paw_region = QtGui.QRegion(paw_rect)
            mask_region = mask_region.united(paw_region)

        # Uncomment this to enforce the mask. Comment it out to see if paw prints appear.
        self.setMask(mask_region)

def main():
    app = QtWidgets.QApplication(sys.argv)
    desktop_sprite = DesktopSprite("image.png", "paw.png")
    desktop_sprite.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
