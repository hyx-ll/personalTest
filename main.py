import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import os
from concurrent.futures import ThreadPoolExecutor
import copy

class VisualBatchImageCropper:
    def __init__(self, root):
        self.root = root
        self.root.title("批量图片裁剪工具")
        self.root.geometry("1000x700")
        self.root.resizable(True, True)

        # 核心数据初始化
        self.image_paths = []
        self.current_img_idx = -1
        self.current_img = None
        self.current_img_tk = None
        self.crop_box = None
        self.is_dragging = False
        self.is_resizing = False
        self.drag_start = (0, 0)
        self.scale = 1.0
        self.img_x = 0
        self.img_y = 0

        # 先初始化UI，再刷新
        self._build_ui()
        self.root.update_idletasks()

    def _build_ui(self):
        """重构UI，确保所有按钮可见"""
        main_container = ttk.Frame(self.root, padding="10")
        main_container.pack(fill=tk.BOTH, expand=True)

        # 1. 左侧预览区
        preview_pane = ttk.Frame(main_container)
        preview_pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        preview_label = ttk.Label(preview_pane, text="图片预览与裁剪操作", font=("Arial", 12, "bold"))
        preview_label.pack(anchor=tk.W, pady=(0, 5))

        tips_label = ttk.Label(
            preview_pane,
            text="操作说明：1. 添加图片后选中预览 2. 点击图片拖动创建裁剪框 3. 拖动框内移动 4. 拖动边框调整大小",
            foreground="#666",
            wraplength=700  # 自动换行，避免挤压
        )
        tips_label.pack(anchor=tk.W, pady=(0, 5))

        self.canvas = tk.Canvas(
            preview_pane,
            bg="#f0f0f0",
            bd=2,
            relief=tk.SUNKEN,
            width=600,
            height=500
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        self.crop_status = ttk.Label(preview_pane, text="当前状态：未添加图片", foreground="#333")
        self.crop_status.pack(anchor=tk.W, pady=(0, 5))

        # 2. 右侧控制区（不固定宽度，允许自适应）
        control_pane = ttk.Frame(main_container)
        control_pane.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        # 取消固定宽度，让组件自然排列
        # control_pane.pack_propagate(False)

        control_label = ttk.Label(control_pane, text="控制中心", font=("Arial", 12, "bold"))
        control_label.pack(anchor=tk.W, pady=(0, 10))

        # 图片列表区域
        list_frame = ttk.LabelFrame(control_pane, text="待裁剪图片", padding="5")
        list_frame.pack(fill=tk.X, pady=(0, 10))

        self.img_listbox = tk.Listbox(list_frame, height=12)
        self.img_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self.img_listbox.bind("<<ListboxSelect>>", self._on_select_image)

        list_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.img_listbox.yview)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.img_listbox.config(yscrollcommand=list_scroll.set)

        # 图片操作按钮
        btn_frame = ttk.Frame(control_pane)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.add_btn = ttk.Button(btn_frame, text="添加图片", command=self._add_images)
        self.add_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.remove_btn = ttk.Button(btn_frame, text="移除选中", command=self._remove_selected)
        self.remove_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.clear_btn = ttk.Button(btn_frame, text="清空列表", command=self._clear_images)
        self.clear_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 输出设置区域（核心修复：调整网格布局，确保按钮可见）
        output_frame = ttk.LabelFrame(control_pane, text="输出设置", padding="5")
        output_frame.pack(fill=tk.X, pady=(0, 10))
        # 调整列权重，让输入框自适应，按钮不被挤压
        output_frame.columnconfigure(1, weight=1)

        ttk.Label(output_frame, text="输出目录：").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.output_dir_var = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "裁剪后的图片"))
        # 缩小输入框宽度，给按钮留空间
        output_entry = ttk.Entry(output_frame, textvariable=self.output_dir_var, width=18)
        output_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        # 按钮单独占一行，避免挤压（关键修复）
        ttk.Button(output_frame, text="选择输出目录", command=self._choose_output_dir).grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky=tk.EW)

        # 批量裁剪按钮
        self.crop_btn = ttk.Button(
            control_pane,
            text="开始批量裁剪",
            command=self._start_batch_crop,
            state=tk.DISABLED,
            style="Accent.TButton"
        )
        self.crop_btn.pack(fill=tk.X, pady=(0, 10), padx=20)

        # 进度条
        self.progress = ttk.Progressbar(control_pane, orient=tk.HORIZONTAL, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(0, 5), padx=20)

        # 绑定画布事件
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

    def _load_image(self, img_path):
        try:
            original_img = Image.open(img_path)
            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()
            max_preview_w = canvas_w * 0.9
            max_preview_h = canvas_h * 0.9

            preview_img = copy.deepcopy(original_img)
            preview_img.thumbnail((max_preview_w, max_preview_h), Image.Resampling.LANCZOS)

            self.scale = preview_img.width / original_img.width if original_img.width != 0 else 1.0
            self.img_x = (canvas_w - preview_img.width) // 2
            self.img_y = (canvas_h - preview_img.height) // 2

            self.current_img_tk = ImageTk.PhotoImage(preview_img)
            self.current_img = original_img
            return True
        except Exception as e:
            messagebox.showerror("图片加载失败", f"文件：{os.path.basename(img_path)}\n原因：{str(e)}")
            return False

    def _draw_image_and_crop_box(self):
        self.canvas.delete("all")

        if self.current_img_tk:
            self.canvas.create_image(self.img_x, self.img_y, anchor=tk.NW, image=self.current_img_tk)

        if self.crop_box and self.current_img:
            x1, y1, x2, y2 = self.crop_box
            preview_x1 = self.img_x + x1 * self.scale
            preview_y1 = self.img_y + y1 * self.scale
            preview_x2 = self.img_x + x2 * self.scale
            preview_y2 = self.img_y + y2 * self.scale

            self.canvas.create_rectangle(
                preview_x1, preview_y1, preview_x2, preview_y2,
                outline="#e74c3c", width=3
            )
            self.canvas.create_rectangle(
                preview_x1, preview_y1, preview_x2, preview_y2,
                fill="#e74c3c", stipple="gray50"
            )

            crop_w = x2 - x1
            crop_h = y2 - y1
            self.crop_status.config(
                text=f"当前状态：已创建裁剪框 | 坐标：({x1},{y1})-({x2},{y2}) | 尺寸：{crop_w}x{crop_h}像素"
            )
        elif self.current_img:
            self.crop_status.config(text="当前状态：已加载图片 | 请拖动鼠标创建裁剪框")
        else:
            self.crop_status.config(text="当前状态：未添加图片")

    def _get_mouse_in_image(self, event):
        if not self.current_img_tk:
            return None, None

        rel_x = event.x - self.img_x
        rel_y = event.y - self.img_y

        if 0 <= rel_x <= self.current_img_tk.width() and 0 <= rel_y <= self.current_img_tk.height():
            original_x = int(rel_x / self.scale)
            original_y = int(rel_y / self.scale)
            return original_x, original_y
        return None, None

    def _is_mouse_on_border(self, event):
        if not self.crop_box or not self.current_img_tk:
            return False, None

        x1, y1, x2, y2 = self.crop_box
        preview_x1 = self.img_x + x1 * self.scale
        preview_y1 = self.img_y + y1 * self.scale
        preview_x2 = self.img_x + x2 * self.scale
        preview_y2 = self.img_y + y2 * self.scale

        tolerance = 6
        mx, my = event.x, event.y

        if abs(my - preview_y1) <= tolerance and preview_x1 <= mx <= preview_x2:
            return True, "top"
        elif abs(my - preview_y2) <= tolerance and preview_x1 <= mx <= preview_x2:
            return True, "bottom"
        elif abs(mx - preview_x1) <= tolerance and preview_y1 <= my <= preview_y2:
            return True, "left"
        elif abs(mx - preview_x2) <= tolerance and preview_y1 <= my <= preview_y2:
            return True, "right"
        return False, None

    def _on_mouse_down(self, event):
        if not self.current_img:
            return

        original_x, original_y = self._get_mouse_in_image(event)
        if not (original_x and original_y):
            return

        is_border, side = self._is_mouse_on_border(event)
        if is_border:
            self.is_resizing = True
            self.resize_side = side
            self.drag_start = (original_x, original_y)
            self.canvas.config(cursor="sizing")
            return

        if self.crop_box:
            x1, y1, x2, y2 = self.crop_box
            if x1 <= original_x <= x2 and y1 <= original_y <= y2:
                self.is_dragging = True
                self.drag_start = (original_x - x1, original_y - y1)
                self.canvas.config(cursor="fleur")
                return

        self.crop_box = (original_x, original_y, original_x + 150, original_y + 150)
        self._draw_image_and_crop_box()
        self.crop_btn.config(state=tk.NORMAL)

    def _on_mouse_drag(self, event):
        if not self.current_img:
            return

        original_x, original_y = self._get_mouse_in_image(event)
        if not (original_x and original_y):
            return

        if self.is_resizing:
            x1, y1, x2, y2 = self.crop_box
            dx = original_x - self.drag_start[0]
            dy = original_y - self.drag_start[1]

            if self.resize_side == "top":
                new_y1 = max(0, y1 + dy)
                if new_y1 < y2 - 20:
                    y1 = new_y1
            elif self.resize_side == "bottom":
                new_y2 = min(self.current_img.height, y2 + dy)
                if new_y2 > y1 + 20:
                    y2 = new_y2
            elif self.resize_side == "left":
                new_x1 = max(0, x1 + dx)
                if new_x1 < x2 - 20:
                    x1 = new_x1
            elif self.resize_side == "right":
                new_x2 = min(self.current_img.width, x2 + dx)
                if new_x2 > x1 + 20:
                    x2 = new_x2

            self.crop_box = (x1, y1, x2, y2)
            self._draw_image_and_crop_box()
            self.drag_start = (original_x, original_y)

        elif self.is_dragging:
            x1, y1, x2, y2 = self.crop_box
            crop_w = x2 - x1
            crop_h = y2 - y1

            new_x1 = original_x - self.drag_start[0]
            new_y1 = original_y - self.drag_start[1]
            new_x2 = new_x1 + crop_w
            new_y2 = new_y1 + crop_h

            new_x1 = max(0, new_x1)
            new_y1 = max(0, new_y1)
            new_x2 = min(self.current_img.width, new_x2)
            new_y2 = min(self.current_img.height, new_y2)

            self.crop_box = (new_x1, new_y1, new_x2, new_y2)
            self._draw_image_and_crop_box()

    def _on_mouse_up(self, event):
        self.is_dragging = False
        self.is_resizing = False
        self.canvas.config(cursor="arrow")

    def _on_canvas_resize(self, event):
        if self.current_img_idx >= 0 and self.image_paths:
            self._load_and_show_image(self.current_img_idx)

    def _on_select_image(self, event):
        selected = self.img_listbox.curselection()
        if not selected:
            return
        self.current_img_idx = selected[0]
        self._load_and_show_image(self.current_img_idx)

    def _load_and_show_image(self, idx):
        if 0 <= idx < len(self.image_paths):
            img_path = self.image_paths[idx]
            if self._load_image(img_path):
                self._draw_image_and_crop_box()
                self.crop_btn.config(state=tk.NORMAL if self.crop_box else tk.DISABLED)

    def _add_images(self):
        file_types = (("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif"), ("所有文件", "*.*"))
        paths = filedialog.askopenfilenames(title="选择要裁剪的图片", filetypes=file_types)
        if paths:
            new_paths = [p for p in paths if p not in self.image_paths]
            self.image_paths.extend(new_paths)
            for path in new_paths:
                self.img_listbox.insert(tk.END, os.path.basename(path))
            if len(self.image_paths) == len(new_paths):
                self.img_listbox.selection_set(0)
                self.current_img_idx = 0
                self._load_and_show_image(0)

    def _remove_selected(self):
        selected = self.img_listbox.curselection()
        if not selected:
            messagebox.showwarning("警告", "请先选中要移除的图片！")
            return
        for idx in reversed(selected):
            self.img_listbox.delete(idx)
            del self.image_paths[idx]
        if self.current_img_idx in selected:
            self.current_img = None
            self.current_img_tk = None
            self.crop_box = None
            self.current_img_idx = -1
            self._draw_image_and_crop_box()
        self.crop_btn.config(state=tk.DISABLED if not self.image_paths or not self.crop_box else tk.NORMAL)

    def _clear_images(self):
        self.image_paths.clear()
        self.img_listbox.delete(0, tk.END)
        self.current_img = None
        self.current_img_tk = None
        self.crop_box = None
        self.current_img_idx = -1
        self._draw_image_and_crop_box()
        self.crop_btn.config(state=tk.DISABLED)

    def _choose_output_dir(self):
        dir_path = filedialog.askdirectory(title="选择裁剪结果保存目录")
        if dir_path:
            self.output_dir_var.set(dir_path)

    def _crop_single_image(self, img_path, crop_box, output_dir):
        try:
            with Image.open(img_path) as img:
                x1, y1, x2, y2 = crop_box
                img_w, img_h = img.size
                x1 = max(0, min(x1, img_w - 20))
                y1 = max(0, min(y1, img_h - 20))
                x2 = max(x1 + 20, min(x2, img_w))
                y2 = max(y1 + 20, min(y2, img_h))

                cropped = img.crop((x1, y1, x2, y2))
                img_name = os.path.basename(img_path)
                output_path = os.path.join(output_dir, img_name)

                if os.path.exists(output_path):
                    name, ext = os.path.splitext(img_name)
                    i = 1
                    while os.path.exists(os.path.join(output_dir, f"{name}_crop{i}{ext}")):
                        i += 1
                    output_path = os.path.join(output_dir, f"{name}_crop{i}{ext}")

                cropped.save(output_path, quality=95)
            return True, img_path
        except Exception as e:
            return False, f"{os.path.basename(img_path)}: {str(e)}"

    def _start_batch_crop(self):
        if not self.image_paths:
            messagebox.showwarning("警告", "请先添加要裁剪的图片！")
            return
        if not self.crop_box:
            messagebox.showwarning("警告", "请先创建裁剪框！")
            return

        output_dir = self.output_dir_var.get()
        os.makedirs(output_dir, exist_ok=True)

        self.crop_btn.config(state=tk.DISABLED)
        self.progress["value"] = 0
        total = len(self.image_paths)
        success = 0
        fails = []

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(self._crop_single_image, path, self.crop_box, output_dir)
                for path in self.image_paths
            ]

            for i, future in enumerate(futures, 1):
                res, msg = future.result()
                if res:
                    success += 1
                else:
                    fails.append(msg)
                self.progress["value"] = (i / total) * 100
                self.root.update_idletasks()

        self.crop_btn.config(state=tk.NORMAL)
        result = f"批量裁剪完成！\n成功：{success} 张\n失败：{len(fails)} 张\n保存目录：{output_dir}"
        if fails:
            result += "\n\n失败详情：\n" + "\n".join(fails[:5])
        messagebox.showinfo("裁剪结果", result)

if __name__ == "__main__":
    try:
        from PIL import Image, ImageTk
    except ImportError:
        import tkinter.messagebox as msgbox
        msgbox.showerror("依赖缺失", "请先安装 Pillow 库：\n在命令行执行：pip install pillow")
    else:
        root = tk.Tk()
        style = ttk.Style(root)
        style.theme_use("clam")
        app = VisualBatchImageCropper(root)
        root.mainloop()