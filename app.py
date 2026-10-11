import sys
import math
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QPushButton, QGroupBox, QFrame, QComboBox,
    QStackedWidget, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPolygonF,
    QPainterPath, QLinearGradient, QRadialGradient
)

# =====================================================================
# HELPER WIDGETS
# =====================================================================

class LiveGraphWidget(QWidget):
    """A custom widget that draws a live-updating line graph."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.datasets = {}  # {name: (color, [values])}
        self.max_points = 300
        self._max_val = 100.0

    def add_dataset(self, name, color):
        self.datasets[name] = (color, [])

    def clear_data(self):
        for name in self.datasets:
            self.datasets[name] = (self.datasets[name][0], [])
        self._max_val = 100.0
        self.update()

    def push_data(self, name, value):
        if name in self.datasets:
            color, data = self.datasets[name]
            data.append(value)
            if len(data) > self.max_points:
                data.pop(0)
            self.datasets[name] = (color, data)
            # Auto-scale Y axis
            current_max = max([abs(v) for d in self.datasets.values() for v in d[1]] or [1.0])
            if current_max > self._max_val * 0.85 or current_max < self._max_val * 0.4:
                # BUG FIX: Ensure _max_val never drops to 0 to prevent ZeroDivisionError
                self._max_val = max(current_max * 1.2, 1.0)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Background
        p.fillRect(self.rect(), QColor(25, 25, 40))
        p.setPen(QPen(QColor(60, 60, 80), 1))
        p.drawRect(0, 0, w-1, h-1)

        margin_l, margin_r, margin_t, margin_b = 50, 20, 20, 20
        gw = w - margin_l - margin_r
        gh = h - margin_t - margin_b

        # BUG FIX: Safety fallback to prevent any chance of division by zero
        safe_max_val = self._max_val if self._max_val != 0 else 1.0

        # Grid and Axes
        p.setPen(QPen(QColor(60, 60, 80), 1, Qt.DotLine))
        for i in range(5):
            y = margin_t + i * (gh / 4)
            p.drawLine(margin_l, int(y), margin_l + gw, int(y))
            val = safe_max_val - (i / 4) * 2 * safe_max_val
            p.setPen(QColor(150, 150, 170))
            p.setFont(QFont("Consolas", 7))
            p.drawText(0, int(y) - 5, margin_l - 5, 15, Qt.AlignRight | Qt.AlignVCenter, f"{val:.0f}")
            p.setPen(QPen(QColor(60, 60, 80), 1, Qt.DotLine))

        # Center line (0)
        p.setPen(QPen(QColor(100, 100, 120), 1, Qt.DashLine))
        y_zero = margin_t + gh / 2
        p.drawLine(margin_l, int(y_zero), margin_l + gw, int(y_zero))

        # Plot Lines
        for name, (color, data) in self.datasets.items():
            if len(data) < 2:
                continue
            path = QPainterPath()
            for i, val in enumerate(data):
                x = margin_l + (i / (self.max_points - 1)) * gw
                # Map val from [-max, max] to [margin_t + gh, margin_t]
                y = y_zero - (val / safe_max_val) * (gh / 2)
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            p.setPen(QPen(color, 2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

        # Legend
        p.setFont(QFont("Arial", 9, QFont.Bold))
        lx = margin_l + 10
        for name, (color, _) in self.datasets.items():
            p.setPen(color)
            p.drawText(lx, margin_t + 15, name)
            lx += 80

        p.end()


class ForceLegendWidget(QWidget):
    """Custom widget to draw the force legend properly."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self._fd = {}

    def set_forces(self, fd):
        self._fd = fd
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(28, 28, 48))

        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Arial", 13, QFont.Bold))
        p.drawText(QRectF(0, 6, w, 24), Qt.AlignCenter, "Force Legend")

        y = 34
        for name, val in self._fd.items():
            color = QColor(200, 200, 200)
            if name in ("weight", "gravity_par", "gravity_perp"): color = QColor(255, 70, 70)
            elif name == "normal": color = QColor(70, 230, 70)
            elif name in ("applied", "spring"): color = QColor(0, 200, 255)
            elif name in ("friction", "damping", "drag"): color = QColor(255, 100, 255)
            elif name == "net": color = QColor(255, 255, 255)

            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(8, y, 18, 14, 3, 3)
            p.setPen(QColor(210, 210, 220))
            p.setFont(QFont("Arial", 10))
            p.drawText(32, y + 12, name.capitalize())
            p.setPen(color)
            p.setFont(QFont("Consolas", 10, QFont.Bold))
            p.drawText(w - 85, y + 12, f"{val:7.2f} N")
            y += 24
        p.end()


# =====================================================================
# BASE SIMULATION LOGIC
# =====================================================================

class PhysicsSimBase(QWidget):
    """Base class for all physics simulations."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.g = 9.81
        self.dt = 1.0 / 60.0
        self.time_elapsed = 0.0
        self.running = False
        
        self.ke = 0.0
        self.pe = 0.0
        self.te = 0.0
        
        self.show_forces = True
        self.show_components = True

    def reset(self):
        self.time_elapsed = 0.0
        self.ke = 0.0
        self.pe = 0.0
        self.te = 0.0
        self.update()

    def step(self):
        if not self.running:
            return
        self.calculate_step()
        self.time_elapsed += self.dt
        self.update()

    def calculate_step(self):
        pass

    def get_forces_dict(self):
        return {}

    def draw_arrow(self, p, x1, y1, x2, y2, color, label="", pen_style=Qt.SolidLine, width=3):
        start, end = QPointF(x1, y1), QPointF(x2, y2)
        p.setPen(QPen(color, width, pen_style))
        p.drawLine(start, end)
        
        # Arrowhead
        dx, dy = x2 - x1, y2 - y1
        ln = math.hypot(dx, dy)
        if ln < 1: return
        ux, uy = dx / ln, dy / ln
        sz = 12
        p1 = QPointF(end.x() - ux*sz - uy*sz*0.38, end.y() - uy*sz + ux*sz*0.38)
        p2 = QPointF(end.x() - ux*sz + uy*sz*0.38, end.y() - uy*sz - ux*sz*0.38)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPolygon(QPolygonF([end, p1, p2]))

        # Label offset perpendicular
        if label:
            ox, oy = -dy/ln * 16, dx/ln * 16
            p.setPen(color)
            p.setFont(QFont("Arial", 10, QFont.Bold))
            p.drawText(int((x1+x2)/2 + ox), int((y1+y2)/2 + oy), label)


# =====================================================================
# SIMULATION 1: INCLINE PLANE
# =====================================================================

class InclineSim(PhysicsSimBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mass = 5.0
        self.applied_force = 30.0
        self.friction_coeff = 0.2
        self.incline_angle = 30.0
        self.position = 0.0
        self.velocity = 0.0
        
        self._inc_start = (0, 0)
        self._inc_len_px = 0
        self._obj_center = (0, 0)

    def reset(self):
        self.position = 0.0
        self.velocity = 0.0
        super().reset()

    def calculate_step(self):
        a_rad = math.radians(self.incline_angle)
        N = self.mass * self.g * math.cos(a_rad)
        grav_par = self.mass * self.g * math.sin(a_rad)
        f_kinetic = self.friction_coeff * N

        net = self.applied_force - grav_par
        if abs(self.velocity) > 0.05:
            net -= math.copysign(f_kinetic, self.velocity)
        else:
            if abs(net) <= f_kinetic:
                net = 0.0
                self.velocity = 0.0
            else:
                net -= math.copysign(f_kinetic, net)

        acc = net / self.mass
        self.velocity += acc * self.dt
        self.position += self.velocity * self.dt

        if self.position < 0:
            self.position = 0.0
            self.velocity = max(0.0, self.velocity)
        if self.position > 60:
            self.position = 60.0
            self.velocity = min(0.0, self.velocity)

        h = self.position * math.sin(a_rad)
        self.ke = 0.5 * self.mass * self.velocity**2
        self.pe = self.mass * self.g * h
        self.te = self.ke + self.pe

    def get_forces_dict(self):
        a = math.radians(self.incline_angle)
        N = self.mass * self.g * math.cos(a)
        gp = self.mass * self.g * math.sin(a)
        fk = self.friction_coeff * N
        net = self.applied_force - gp
        if abs(self.velocity) > 0.05:
            net -= math.copysign(fk, self.velocity)
        elif abs(net) <= fk:
            net = 0.0
        else:
            net -= math.copysign(fk, net)
        return dict(weight=self.mass*self.g, normal=N, gravity_par=gp, 
                    gravity_perp=N, applied=self.applied_force, friction=fk, net=net)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        
        # Background
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0, QColor(20, 20, 45))
        bg.setColorAt(1, QColor(35, 35, 60))
        p.fillRect(self.rect(), bg)

        # Incline
        a = math.radians(self.incline_angle)
        margin = 70
        bx, by = margin, h - margin
        length = w - 2 * margin
        tx = bx + length * math.cos(a)
        ty = by - length * math.sin(a)

        p.setPen(QPen(QColor(110, 110, 130), 2))
        p.drawLine(int(bx), int(by), int(w-margin), int(by))

        path = QPainterPath()
        path.moveTo(bx, by)
        path.lineTo(tx, ty)
        path.lineTo(bx, by)
        p.fillPath(path, QColor(65, 65, 95, 180))
        p.setPen(QPen(QColor(160, 160, 200), 3))
        p.drawLine(int(bx), int(by), int(tx), int(ty))

        # Angle Arc
        p.setPen(QPen(QColor(255, 230, 80), 2))
        r = 55
        p.drawArc(int(bx-r), int(by-r), r*2, r*2, 0, int(-self.incline_angle*16))
        la = math.radians(self.incline_angle/2)
        p.setFont(QFont("Arial", 11, QFont.Bold))
        p.drawText(int(bx + (r+18)*math.cos(la)), int(by - (r+18)*math.sin(la)), f"{self.incline_angle:.0f}°")

        self._inc_start = (bx, by)
        self._inc_len_px = length

        # Object
        ratio = self.position / 60.0
        px = ratio * (length - 50) + 25
        cx = bx + px * math.cos(a)
        cy = by - px * math.sin(a)
        self._obj_center = (cx, cy)
        sz = 26

        rg = QRadialGradient(QPointF(cx-4, cy-4), sz*1.4)
        rg.setColorAt(0, QColor(100, 170, 255))
        rg.setColorAt(1, QColor(30, 70, 180))
        p.setBrush(rg)
        p.setPen(QPen(QColor(130, 190, 255), 2))
        p.drawEllipse(QPointF(cx, cy), sz, sz)
        
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Arial", 10, QFont.Bold))
        p.drawText(QRectF(cx-14, cy-8, 28, 16), Qt.AlignCenter, f"{self.mass:.0f}")

        # Velocity Vector
        if abs(self.velocity) > 0.15:
            v_scale = 2.5
            vl = self.velocity * v_scale
            ex = cx + vl * math.cos(a)
            ey = cy - vl * math.sin(a)
            self.draw_arrow(p, cx, cy, ex, ey, QColor(255, 255, 80), f"v={self.velocity:.1f}", Qt.DashLine, 2)

        # Forces
        fd = self.get_forces_dict()
        if self.show_forces:
            max_f = max(fd['weight'], fd['normal'], fd['applied'], fd['gravity_par'], fd['friction'], 1)
            scale = 120.0 / max_f

            # Weight
            self.draw_arrow(p, cx, cy, cx, cy + fd['weight']*scale, QColor(255, 70, 70), "W")
            # Normal
            nl = fd['normal']*scale
            self.draw_arrow(p, cx, cy, cx - math.sin(a)*nl, cy - math.cos(a)*nl, QColor(70, 230, 70), "N")
            # Applied
            if abs(fd['applied']) > 0.1:
                al = fd['applied']*scale
                self.draw_arrow(p, cx, cy, cx + math.cos(a)*al, cy - math.sin(a)*al, QColor(0, 200, 255), "F_app")
            # Components
            if self.show_components:
                gl = fd['gravity_par']*scale
                self.draw_arrow(p, cx, cy, cx - math.cos(a)*gl, cy + math.sin(a)*gl, QColor(255, 160, 50), "mg sinθ")
                gl2 = fd['gravity_perp']*scale
                self.draw_arrow(p, cx, cy, cx + math.sin(a)*gl2, cy + math.cos(a)*gl2, QColor(255, 190, 110), "mg cosθ")
            # Friction
            if fd['friction'] > 0.1:
                direction = -1 if self.velocity > 0.05 else (1 if self.velocity < -0.05 else (-1 if fd['applied'] - fd['gravity_par'] > 0 else 1))
                fl = fd['friction']*scale*direction
                self.draw_arrow(p, cx, cy, cx + math.cos(a)*fl, cy - math.sin(a)*fl, QColor(255, 100, 255), "f")
            # Net
            nl2 = fd['net']*scale
            if abs(nl2) > 2:
                self.draw_arrow(p, cx, cy, cx + math.cos(a)*nl2, cy - math.sin(a)*nl2, QColor(255, 255, 255), "F_net", Qt.DashLine, 3)

        # HUD
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawRoundedRect(10, 10, 230, 130, 10, 10)
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Consolas", 11))
        ht = self.position * math.sin(a)
        acc = fd.get('net', 0) / self.mass if self.mass else 0
        lines = [
            f"Time     : {self.time_elapsed:7.1f} s",
            f"Position : {self.position:7.2f} m",
            f"Velocity : {self.velocity:7.2f} m/s",
            f"Height   : {ht:7.2f} m",
            f"Accel    : {acc:7.2f} m/s²",
            f"KE={self.ke:.1f}  PE={self.pe:.1f} J"
        ]
        y_pos = 30
        for line in lines:
            p.drawText(20, y_pos, line)
            y_pos += 19

        p.end()


# =====================================================================
# SIMULATION 2: FREE FALL WITH AIR RESISTANCE
# =====================================================================

class FreeFallSim(PhysicsSimBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mass = 10.0
        self.drag_coeff = 0.5
        self.velocity = 0.0
        self.position = 0.0
        self.max_height = 200.0
        
    def reset(self):
        self.velocity = 0.0
        self.position = self.max_height
        super().reset()

    def calculate_step(self):
        weight = self.mass * self.g
        drag = self.drag_coeff * self.velocity * abs(self.velocity)
        net_force = weight - drag
        acc = net_force / self.mass
        
        self.velocity += acc * self.dt
        self.position -= self.velocity * self.dt
        
        if self.position <= 0:
            self.position = 0
            self.velocity = 0
            
        self.ke = 0.5 * self.mass * self.velocity**2
        self.pe = self.mass * self.g * self.position
        self.te = self.ke + self.pe

    def get_forces_dict(self):
        weight = self.mass * self.g
        drag = self.drag_coeff * self.velocity * abs(self.velocity)
        net = weight - drag
        return dict(weight=weight, drag=drag, net=net)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(20, 25, 45))

        margin_l, margin_b = 80, 60
        top_y = 40
        ruler_h = h - margin_b - top_y
        
        p.setPen(QPen(QColor(100, 100, 130), 2))
        p.drawLine(margin_l, top_y, margin_l, top_y + ruler_h)
        p.drawLine(margin_l, top_y + ruler_h, w - 40, top_y + ruler_h)
        
        p.setFont(QFont("Consolas", 8))
        p.setPen(QColor(150, 150, 170))
        for i in range(0, int(self.max_height) + 1, 20):
            y = top_y + ruler_h - (i / self.max_height) * ruler_h
            p.drawText(10, int(y) + 4, f"{i}m")
            p.setPen(QPen(QColor(60, 60, 80), 1, Qt.DotLine))
            p.drawLine(margin_l, int(y), w - 40, int(y))
            p.setPen(QColor(150, 150, 170))

        obj_y = top_y + ruler_h - (self.position / self.max_height) * ruler_h
        obj_x = w / 2
        sz = 20
        
        rg = QRadialGradient(QPointF(obj_x-3, obj_y-3), sz*1.4)
        rg.setColorAt(0, QColor(255, 120, 120))
        rg.setColorAt(1, QColor(180, 30, 30))
        p.setBrush(rg)
        p.setPen(QPen(QColor(255, 150, 150), 2))
        p.drawEllipse(QPointF(obj_x, obj_y), sz, sz)

        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Arial", 9, QFont.Bold))
        p.drawText(QRectF(obj_x-12, obj_y-6, 24, 12), Qt.AlignCenter, f"{self.mass:.0f}")

        fd = self.get_forces_dict()
        if self.show_forces:
            max_f = max(fd['weight'], 1)
            scale = 100.0 / max_f
            
            self.draw_arrow(p, obj_x, obj_y, obj_x, obj_y + fd['weight']*scale, QColor(255, 70, 70), "W")
            if fd['drag'] > 0.1:
                self.draw_arrow(p, obj_x, obj_y, obj_x, obj_y - fd['drag']*scale, QColor(70, 230, 70), "F_drag")
            if abs(fd['net']) > 0.5:
                self.draw_arrow(p, obj_x+30, obj_y, obj_x+30, obj_y + fd['net']*scale, QColor(255, 255, 255), "F_net", Qt.DashLine, 3)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawRoundedRect(w-240, 10, 230, 130, 10, 10)
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Consolas", 11))
        acc = fd.get('net', 0) / self.mass if self.mass else 0
        lines = [
            f"Time     : {self.time_elapsed:7.1f} s",
            f"Height   : {self.position:7.2f} m",
            f"Velocity : {self.velocity:7.2f} m/s",
            f"Accel    : {acc:7.2f} m/s²",
            f"Term. V  : {math.sqrt(self.mass*self.g/max(self.drag_coeff, 0.01)):7.2f} m/s",
            f"KE={self.ke:.1f}  PE={self.pe:.1f} J"
        ]
        y_pos = 30
        for line in lines:
            p.drawText(w-230, y_pos, line)
            y_pos += 19

        p.end()


# =====================================================================
# SIMULATION 3: SPRING HARMONIC OSCILLATOR
# =====================================================================

class SpringSim(PhysicsSimBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mass = 2.0
        self.spring_k = 20.0
        self.damping = 0.1
        self.displacement = 50.0
        self.velocity = 0.0
        
    def reset(self):
        self.displacement = 50.0
        self.velocity = 0.0
        super().reset()

    def calculate_step(self):
        spring_force = -self.spring_k * self.displacement
        damping_force = -self.damping * self.velocity
        net_force = spring_force + damping_force
        
        acc = net_force / self.mass
        self.velocity += acc * self.dt
        self.displacement += self.velocity * self.dt
        
        self.pe = 0.5 * self.spring_k * self.displacement**2
        self.ke = 0.5 * self.mass * self.velocity**2
        self.te = self.ke + self.pe

    def get_forces_dict(self):
        spring_f = -self.spring_k * self.displacement
        damp_f = -self.damping * self.velocity
        net = spring_f + damp_f
        return dict(spring=spring_f, damping=damp_f, net=net)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(20, 30, 25))

        wall_x = 80
        p.setPen(QPen(QColor(150, 150, 150), 3))
        p.drawLine(wall_x, 100, wall_x, h - 100)
        p.setPen(QPen(QColor(100, 100, 100), 1))
        for i in range(100, h-100, 15):
            p.drawLine(wall_x, i, wall_x - 15, i + 15)

        eq_x = w / 2
        obj_x = eq_x + self.displacement * 3
        obj_y = h / 2
        
        p.setPen(QPen(QColor(180, 180, 220), 2))
        path = QPainterPath()
        path.moveTo(wall_x, obj_y)
        num_coils = 15
        coil_width = (obj_x - 30 - wall_x) / num_coils
        for i in range(num_coils):
            cy = obj_y + (15 if i % 2 == 0 else -15)
            path.lineTo(wall_x + (i+0.5)*coil_width, cy)
        path.lineTo(obj_x - 30, obj_y)
        p.drawPath(path)

        sz = 30
        rg = QRadialGradient(QPointF(obj_x-4, obj_y-4), sz*1.4)
        rg.setColorAt(0, QColor(120, 255, 120))
        rg.setColorAt(1, QColor(30, 180, 30))
        p.setBrush(rg)
        p.setPen(QPen(QColor(150, 255, 150), 2))
        p.drawRect(QRectF(obj_x - sz, obj_y - sz, sz*2, sz*2))

        p.setPen(QColor(20, 50, 20))
        p.setFont(QFont("Arial", 10, QFont.Bold))
        p.drawText(QRectF(obj_x-sz, obj_y-8, sz*2, 16), Qt.AlignCenter, f"{self.mass:.0f}kg")

        p.setPen(QPen(QColor(255, 255, 255, 80), 1, Qt.DashLine))
        p.drawLine(int(eq_x), 100, int(eq_x), h-100)
        p.setPen(QColor(200, 200, 200))
        p.setFont(QFont("Arial", 9))
        p.drawText(int(eq_x)-20, 90, "x = 0")

        fd = self.get_forces_dict()
        if self.show_forces:
            max_f = max(abs(fd['spring']), abs(fd['damping']), 1)
            scale = 100.0 / max_f
            
            if abs(fd['spring']) > 0.1:
                self.draw_arrow(p, obj_x, obj_y - 40, obj_x + fd['spring']*scale, obj_y - 40, QColor(0, 200, 255), "F_spring")
            if abs(fd['damping']) > 0.1:
                self.draw_arrow(p, obj_x, obj_y + 40, obj_x + fd['damping']*scale, obj_y + 40, QColor(255, 100, 255), "F_damp")
            if abs(fd['net']) > 0.5:
                self.draw_arrow(p, obj_x, obj_y, obj_x + fd['net']*scale, obj_y, QColor(255, 255, 255), "F_net", Qt.DashLine, 3)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawRoundedRect(w-230, 10, 220, 110, 10, 10)
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Consolas", 11))
        lines = [
            f"Time     : {self.time_elapsed:7.1f} s",
            f"Displ.   : {self.displacement:7.2f} m",
            f"Velocity : {self.velocity:7.2f} m/s",
            f"KE={self.ke:.1f}  PE={self.pe:.1f} J"
        ]
        y_pos = 30
        for line in lines:
            p.drawText(w-220, y_pos, line)
            y_pos += 22

        p.end()


# =====================================================================
# MAIN WINDOW
# =====================================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("⚡ Complete Force & Motion Physics Simulator")
        self.setMinimumSize(1300, 850)
        self.setStyleSheet(STYLESHEET)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setSpacing(10)

        # --- Left Panel (Simulations + Controls) ---
        left_panel = QVBoxLayout()
        
        # Mode Selector
        mode_layout = QHBoxLayout()
        mode_label = QLabel("Scenario:")
        mode_label.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Incline Plane", "Free Fall (Drag)", "Spring Oscillator"])
        self.mode_combo.currentIndexChanged.connect(self.switch_simulation)
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_combo, stretch=1)
        left_panel.addLayout(mode_layout)

        # Stacked Simulations
        self.sim_stack = QStackedWidget()
        self.sim_incline = InclineSim()
        self.sim_freefall = FreeFallSim()
        self.sim_spring = SpringSim()
        self.sim_stack.addWidget(self.sim_incline)
        self.sim_stack.addWidget(self.sim_freefall)
        self.sim_stack.addWidget(self.sim_spring)
        left_panel.addWidget(self.sim_stack, stretch=4)

        # Controls Area
        self.ctrl_stack = QStackedWidget()
        self.ctrl_stack.addWidget(self._build_incline_ctrls())
        self.ctrl_stack.addWidget(self._build_freefall_ctrls())
        self.ctrl_stack.addWidget(self._build_spring_ctrls())
        left_panel.addWidget(self.ctrl_stack, stretch=1)
        
        # Global Controls
        global_ctrls = QHBoxLayout()
        self.play_btn = QPushButton("▶  Play")
        self.play_btn.setCheckable(True)
        self.play_btn.setMinimumWidth(100)
        self.play_btn.clicked.connect(self.toggle_play)
        
        self.rst_btn = QPushButton("⟳  Reset")
        self.rst_btn.setMinimumWidth(100)
        self.rst_btn.clicked.connect(self.reset_sim)

        self.force_btn = QPushButton("⇀  Forces")
        self.force_btn.setCheckable(True)
        self.force_btn.setChecked(True)
        self.force_btn.clicked.connect(lambda c: self._active_sim().show_forces(c))

        self.comp_btn = QPushButton("⊞  Components")
        self.comp_btn.setCheckable(True)
        self.comp_btn.setChecked(True)
        self.comp_btn.clicked.connect(lambda c: self._active_sim().show_components(c))

        global_ctrls.addWidget(self.play_btn)
        global_ctrls.addWidget(self.rst_btn)
        global_ctrls.addWidget(self.force_btn)
        global_ctrls.addWidget(self.comp_btn)
        left_panel.addLayout(global_ctrls)

        root.addLayout(left_panel, stretch=3)

        # --- Right Panel (Graphs & Info) ---
        right_panel = QVBoxLayout()
        
        # Energy Graph
        self.graph = LiveGraphWidget()
        self.graph.add_dataset("KE", QColor(255, 110, 50))
        self.graph.add_dataset("PE", QColor(50, 210, 100))
        self.graph.add_dataset("Total", QColor(110, 150, 255))
        right_panel.addWidget(self.graph, stretch=2)

        # Force Legend
        self.legend_w = ForceLegendWidget()
        right_panel.addWidget(self.legend_w, stretch=1)

        # Formulas
        right_panel.addWidget(self._build_formulas(), stretch=1)

        root.addLayout(right_panel, stretch=2)

        # Timer
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)

        # Initial Sync
        self.switch_simulation(0)

    def _active_sim(self):
        return self.sim_stack.currentWidget()

    def switch_simulation(self, index):
        was_running = self.timer.isActive()
        if was_running:
            self.toggle_play(False)
            
        self.sim_stack.setCurrentIndex(index)
        self.ctrl_stack.setCurrentIndex(index)
        self.reset_sim()
        self.graph.clear_data()

    def toggle_play(self, checked):
        if checked:
            self.play_btn.setText("⏸  Pause")
            self._active_sim().running = True
            self.timer.start()
        else:
            self.play_btn.setText("▶  Play")
            self._active_sim().running = False
            self.timer.stop()

    def reset_sim(self):
        self._active_sim().reset()
        self.graph.clear_data()
        self.legend_w.set_forces(self._active_sim().get_forces_dict())

    def tick(self):
        sim = self._active_sim()
        sim.step()
        
        self.graph.push_data("KE", sim.ke)
        self.graph.push_data("PE", sim.pe)
        self.graph.push_data("Total", sim.te)
        self.graph.update()
        
        self.legend_w.set_forces(sim.get_forces_dict())

    def _make_slider(self, title, lo, hi, default, callback):
        g = QGroupBox(title)
        v = QVBoxLayout()
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(default)
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter)
        s.valueChanged.connect(lambda val: callback(val, lbl))
        callback(default, lbl)
        v.addWidget(s)
        v.addWidget(lbl)
        g.setLayout(v)
        return g

    def _build_incline_ctrls(self):
        f = QFrame()
        lay = QHBoxLayout(f)
        lay.addWidget(self._make_slider("Mass (kg)", 1, 50, 5, 
                        lambda v, l: (setattr(self.sim_incline, 'mass', float(v)), l.setText(f"{v} kg"))))
        lay.addWidget(self._make_slider("Applied (N)", 0, 500, 30, 
                        lambda v, l: (setattr(self.sim_incline, 'applied_force', float(v)), l.setText(f"{v} N"))))
        lay.addWidget(self._make_slider("Friction μ", 0, 100, 20, 
                        lambda v, l: (setattr(self.sim_incline, 'friction_coeff', v/100.0), l.setText(f"{v/100:.2f}"))))
        lay.addWidget(self._make_slider("Angle °", 0, 60, 30, 
                        lambda v, l: (setattr(self.sim_incline, 'incline_angle', float(v)), l.setText(f"{v}°"))))
        return f

    def _build_freefall_ctrls(self):
        f = QFrame()
        lay = QHBoxLayout(f)
        lay.addWidget(self._make_slider("Mass (kg)", 1, 100, 10, 
                        lambda v, l: (setattr(self.sim_freefall, 'mass', float(v)), l.setText(f"{v} kg"))))
        lay.addWidget(self._make_slider("Air Drag (k)", 0, 200, 50, 
                        lambda v, l: (setattr(self.sim_freefall, 'drag_coeff', v/100.0), l.setText(f"{v/100:.2f}"))))
        return f

    def _build_spring_ctrls(self):
        f = QFrame()
        lay = QHBoxLayout(f)
        lay.addWidget(self._make_slider("Mass (kg)", 1, 20, 2, 
                        lambda v, l: (setattr(self.sim_spring, 'mass', float(v)), l.setText(f"{v} kg"))))
        lay.addWidget(self._make_slider("Spring k", 1, 200, 20, 
                        lambda v, l: (setattr(self.sim_spring, 'spring_k', float(v)), l.setText(f"{v} N/m"))))
        lay.addWidget(self._make_slider("Damping", 0, 100, 10, 
                        lambda v, l: (setattr(self.sim_spring, 'damping', v/10.0), l.setText(f"{v/10:.1f}"))))
        return f

    def _build_formulas(self):
        g = QGroupBox("📐  Key Formulas")
        v = QVBoxLayout()
        formulas = [
            ("Newton's 2nd Law", "F_net = m·a"),
            ("Weight", "W = m·g"),
            ("Kinetic Energy", "KE = ½·m·v²"),
            ("Gravitational PE", "PE_g = m·g·h"),
            ("Elastic PE", "PE_e = ½·k·x²"),
            ("Friction", "f_k = μ_k·N"),
            ("Drag Force", "F_d = ½·C_d·ρ·A·v²"),
            ("Hooke's Law", "F_s = -k·x"),
        ]
        for title, eq in formulas:
            lbl = QLabel(f"<b style='color:#99bbff'>{title}:</b>  <span style='color:#ffdd66'>{eq}</span>")
            lbl.setTextFormat(Qt.RichText)
            v.addWidget(lbl)
        g.setLayout(v)
        return g


STYLESHEET = """
QMainWindow, QWidget { background: #1e1e32; }
QGroupBox {
    color: #ccc; border: 1px solid #555; border-radius: 8px;
    margin-top: 14px; padding-top: 14px; font-weight: bold;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
QLabel { color: #ddd; }
QPushButton {
    background: #3a3a5c; color: #eee; border: 1px solid #555;
    border-radius: 5px; padding: 7px 14px; font-weight: bold; font-size: 13px;
}
QPushButton:hover { background: #4a4a7c; }
QPushButton:pressed { background: #2a2a4c; }
QPushButton:checked { background: #5a5aac; border-color: #8a8aff; }
QSlider::groove:horizontal { height: 8px; background: #3a3a5c; border-radius: 4px; }
QSlider::handle:horizontal { width: 18px; height: 18px; margin: -5px 0; background: #7a7aff; border-radius: 9px; }
QSlider::sub-page:horizontal { background: #5a5aac; border-radius: 4px; }
QFrame { border: 1px solid #444; border-radius: 6px; }
QComboBox {
    background: #3a3a5c; color: white; border: 1px solid #555;
    border-radius: 5px; padding: 5px; font-size: 13px; font-weight: bold;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView { background: #2a2a4c; color: white; selection-background-color: #5a5aac; }
"""

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())