"""
Synthetic P&ID Generator for MRPL Pump P-101 Cooling Water Circuit.
INDUSAI-X / SIH26117
Generates a standard ISA-5.1 compliant industrial P&ID PNG drawing with grid coordinates.
"""

import os
from PIL import Image, ImageDraw, ImageFont


def generate_sample_pid(output_path: str = "samples/PID_Cooling_Water_Circuit_P101.png") -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    width, height = 1920, 1080
    image = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    # 1. Outer Border and Engineering Grid (Rows A-D, Cols 1-6)
    margin = 40
    draw.rectangle([margin, margin, width - margin, height - margin], outline=(0, 0, 0), width=3)
    draw.rectangle([margin + 10, margin + 10, width - margin - 10, height - margin - 10], outline=(0, 0, 0), width=1)

    # Grid lines and labels
    n_cols = 6
    n_rows = 4
    col_w = (width - 2 * margin) / n_cols
    row_h = (height - 2 * margin) / n_rows

    row_labels = ["A", "B", "C", "D"]
    for i, label in enumerate(row_labels):
        y = margin + i * row_h + row_h / 2
        draw.text((margin - 25, y - 10), label, fill=(0, 0, 0))
        draw.text((width - margin + 12, y - 10), label, fill=(0, 0, 0))

    for j in range(n_cols):
        x = margin + j * col_w + col_w / 2
        draw.text((x - 5, margin - 25), str(j + 1), fill=(0, 0, 0))
        draw.text((x - 5, height - margin + 10), str(j + 1), fill=(0, 0, 0))

    # 2. Title Block (Bottom Right Corner)
    tb_w, tb_h = 420, 150
    tb_x0 = width - margin - 10 - tb_w
    tb_y0 = height - margin - 10 - tb_h
    draw.rectangle([tb_x0, tb_y0, tb_x0 + tb_w, tb_y0 + tb_h], outline=(0, 0, 0), width=2, fill=(245, 247, 250))
    draw.line([tb_x0, tb_y0 + 35, tb_x0 + tb_w, tb_y0 + 35], fill=(0, 0, 0), width=1)
    draw.line([tb_x0, tb_y0 + 70, tb_x0 + tb_w, tb_y0 + 70], fill=(0, 0, 0), width=1)
    draw.line([tb_x0, tb_y0 + 105, tb_x0 + tb_w, tb_y0 + 105], fill=(0, 0, 0), width=1)
    draw.line([tb_x0 + 200, tb_y0 + 35, tb_x0 + 200, tb_y0 + tb_h], fill=(0, 0, 0), width=1)

    draw.text((tb_x0 + 15, tb_y0 + 10), "MANGALORE REFINERY & PETROCHEMICALS LTD (MRPL)", fill=(0, 51, 102))
    draw.text((tb_x0 + 15, tb_y0 + 45), "UNIT: CDU-1 / REFINERY UNIT 4", fill=(0, 0, 0))
    draw.text((tb_x0 + 215, tb_y0 + 45), "STATUS: AS-BUILT", fill=(0, 128, 0))
    draw.text((tb_x0 + 15, tb_y0 + 80), "DWG: PID-CW-P101-02", fill=(0, 0, 0))
    draw.text((tb_x0 + 215, tb_y0 + 80), "REV: 04 (APPROVED)", fill=(0, 0, 0))
    draw.text((tb_x0 + 15, tb_y0 + 115), "TITLE: PUMP P-101 COOLING WATER & LUBE CIRCUIT", fill=(0, 0, 0))

    # 3. Main Equipment: Booster Pump P-101 (Grid C2)
    # Circle + discharge nozzle
    p_cx, p_cy = int(margin + 1.5 * col_w), int(margin + 2.5 * row_h)
    p_r = 50
    draw.ellipse([p_cx - p_r, p_cy - p_r, p_cx + p_r, p_cy + p_r], outline=(0, 0, 153), width=3, fill=(230, 240, 255))
    # Tangential discharge nozzle
    draw.polygon([(p_cx + 10, p_cy - p_r), (p_cx + 50, p_cy - p_r - 40), (p_cx + 50, p_cy - p_r)], fill=(0, 0, 153))
    draw.text((p_cx - 25, p_cy - 10), "P-101", fill=(0, 0, 153))
    draw.text((p_cx - 45, p_cy + p_r + 10), "BOOSTER PUMP P-101", fill=(0, 0, 0))

    # 4. Heat Exchanger E-101 (Lube Oil Cooler) (Grid C3)
    e_cx, e_cy = int(margin + 2.8 * col_w), int(margin + 2.5 * row_h)
    e_w, e_h = 100, 60
    draw.rectangle([e_cx - e_w // 2, e_cy - e_h // 2, e_cx + e_w // 2, e_cy + e_h // 2], outline=(153, 0, 0), width=3, fill=(255, 240, 240))
    # Internal tube bundle U-lines
    draw.arc([e_cx - 30, e_cy - 20, e_cx + 30, e_cy + 20], start=0, end=180, fill=(153, 0, 0), width=2)
    draw.text((e_cx - 20, e_cy - 10), "E-101", fill=(153, 0, 0))
    draw.text((e_cx - 45, e_cy + e_h // 2 + 10), "LUBE COOLER E-101", fill=(0, 0, 0))

    # 5. Piping from Pump P-101 to Heat Exchanger E-101
    draw.line([p_cx + p_r, p_cy, e_cx - e_w // 2, e_cy], fill=(0, 102, 204), width=4)
    # Flow arrow
    arrow_x = (p_cx + p_r + e_cx - e_w // 2) // 2
    draw.polygon([(arrow_x, p_cy - 6), (arrow_x + 12, p_cy), (arrow_x, p_cy + 6)], fill=(0, 102, 204))
    draw.text((arrow_x - 30, p_cy - 22), '3"-LO-101-CS', fill=(0, 0, 0))

    # 6. Cooling Water Circuit (Grid D4)
    # Cooling water line entering E-101 and exiting to CV-104B and V-109
    cw_x = int(margin + 4.0 * col_w)
    cw_y_main = int(margin + 2.3 * row_h)    # Main line with CV-104B
    cw_y_bypass = int(margin + 2.8 * row_h)  # Bypass line with V-109

    # Cooling water supply and return lines
    draw.line([e_cx, e_cy - e_h // 2, e_cx, cw_y_main], fill=(0, 153, 76), width=4)
    draw.line([e_cx, cw_y_main, cw_x + 150, cw_y_main], fill=(0, 153, 76), width=4)

    # Bypass split before CV-104B and rejoin after CV-104B
    split_x = cw_x - 60
    rejoin_x = cw_x + 80
    draw.line([split_x, cw_y_main, split_x, cw_y_bypass], fill=(0, 153, 76), width=3)
    draw.line([split_x, cw_y_bypass, rejoin_x, cw_y_bypass], fill=(0, 153, 76), width=3)
    draw.line([rejoin_x, cw_y_bypass, rejoin_x, cw_y_main], fill=(0, 153, 76), width=3)

    # 7. Control Valve CV-104B (Pneumatic Diaphragm Valve Symbol) on main line
    # Two opposing triangles + stem + mushroom actuator
    cv_x, cv_y = cw_x, cw_y_main
    draw.polygon([(cv_x - 20, cv_y - 12), (cv_x, cv_y), (cv_x - 20, cv_y + 12)], fill=(0, 153, 76), outline=(0, 0, 0))
    draw.polygon([(cv_x + 20, cv_y - 12), (cv_x, cv_y), (cv_x + 20, cv_y + 12)], fill=(0, 153, 76), outline=(0, 0, 0))
    draw.line([cv_x, cv_y, cv_x, cv_y - 25], fill=(0, 0, 0), width=2)
    # Actuator cap (half circle/dome)
    draw.arc([cv_x - 18, cv_y - 45, cv_x + 18, cv_y - 25], start=180, end=360, fill=(0, 0, 0), width=2)
    draw.line([cv_x - 18, cv_y - 35, cv_x + 18, cv_y - 35], fill=(0, 0, 0), width=2)
    draw.text((cv_x - 25, cv_y + 18), "CV-104B", fill=(0, 102, 0))
    draw.text((cv_x - 45, cv_y + 35), 'COOLING RETURN (FC)', fill=(0, 0, 0))

    # 8. Manual Isolation Bypass Valve V-109 (Normally Closed - NC) on bypass line
    v_x, v_y = cw_x, cw_y_bypass
    draw.polygon([(v_x - 18, v_y - 10), (v_x, v_y), (v_x - 18, v_y + 10)], fill=(204, 0, 0), outline=(0, 0, 0))
    draw.polygon([(v_x + 18, v_y - 10), (v_x, v_y), (v_x + 18, v_y + 10)], fill=(204, 0, 0), outline=(0, 0, 0))
    draw.line([v_x, v_y, v_x, v_y - 18], fill=(0, 0, 0), width=2)
    draw.line([v_x - 12, v_y - 18, v_x + 12, v_y - 18], fill=(0, 0, 0), width=2)
    # Valve tag and state notation
    draw.text((v_x - 20, v_y + 16), "V-109", fill=(153, 0, 0))
    draw.text((v_x + 22, v_y - 8), "NC", fill=(204, 0, 0))
    draw.text((v_x - 30, v_y + 32), "MANUAL BYPASS (NC)", fill=(0, 0, 0))

    # 9. Transmitter Instruments (PT-201 & TT-301)
    pt_x, pt_y = p_cx + 40, p_cy - 120
    draw.ellipse([pt_x - 22, pt_y - 22, pt_x + 22, pt_y + 22], outline=(0, 0, 0), width=2, fill=(255, 255, 204))
    draw.line([pt_x - 22, pt_y, pt_x + 22, pt_y], fill=(0, 0, 0), width=1)
    draw.text((pt_x - 10, pt_y - 18), "PT", fill=(0, 0, 0))
    draw.text((pt_x - 14, pt_y + 4), "201", fill=(0, 0, 0))
    draw.line([pt_x, pt_y + 22, p_cx + 40, p_cy - p_r], fill=(0, 0, 0), width=1)

    image.save(output_path, format="PNG")
    return output_path


if __name__ == "__main__":
    out = generate_sample_pid()
    print(f"Generated sample P&ID drawing: {out}")
