"""
图形界面版本（tkinter实现）：智慧教育平台资源下载工具
"""

import logging
import sys
import time
import tkinter as tk
import tkinter.font as tkFont
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from tools.downloader import download_files_tk, fetch_all_data
from tools.logo import DESCRIBES, LOGO_TEXT
from tools.parser import extract_resource_url, parse_urls, RESOURCE_DICT
from tools.parser2 import fetch_metadata, gen_url_from_tags, query_metadata
from tools.utils import get_file_path
from tools.utils import base64_to_image
from tools.icons import ICON_LARGE, ICON_SMALL


DEFAULT_PATH = "./downloads"




def display_results(results: list, elapsed_time: float):
    """展示下载结果统计"""
    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = len(results) - success_count

    messages = [
        ["总计文件", str(len(results))],
        ["成功下载", f"{success_count}"],
        ["下载失败", f"{failed_count}"],
        ["总用时", f"{elapsed_time:.1f}秒"],
    ]
    return "\n".join([": ".join(v) for v in messages])


def get_font(families: list, size: int, weight: str = "normal"):
    """获取字体，如果指定字体不可用则返回默认字体"""
    weight = weight.strip().lower()
    if weight not in ["normal", "bold"]:
        weight = "normal"
    try:
        for family in families:
            font = tkFont.Font(family=family, size=size, weight=weight)
            if font.actual("family") == family:
                return (family, size, weight)
    except Exception:
        pass
    return (None, size, weight)


class BookSelectorFrame(ttk.Frame):
    """自定义选择框架"""

    def __init__(self, parent, scale=1.0):
        super().__init__(parent)
        # 初始化属性
        self.hier_dict = None
        self.tag_dict = None
        self.id_dict = None
        self.frame_names = ["选择课本", "选择教材"]
        self.level_hiers = []
        self.level_options = []  # 下拉框数据，[id, name]
        self.wraplength = int(450 * scale)
        self.padx = int(5 * scale)
        self.pady = int(5 * scale)
        self.checkbox_height = int(200 * scale)

        self.selected_items = set()  # 多选框选中的条目
        self.checkbox_list = []  # 多选框
        self.combobox_list = []  # 下拉框

        self.pack(fill=tk.BOTH, expand=True)

        # 创建上下两个部分
        # self.books_frame = ttk.Frame(self)
        self.books_frame = ttk.LabelFrame(self, text=self.frame_names[0], padding=self.padx * 2)
        self.books_frame.pack(fill=tk.BOTH, expand=True, padx=self.padx, pady=self.padx)

        # self.hierarchy_frame = ttk.Frame(self)
        self.hierarchy_frame = ttk.LabelFrame(self, text=self.frame_names[1], padding=self.padx * 2)
        self.hierarchy_frame.pack(fill=tk.BOTH, expand=True, padx=self.padx, pady=self.padx)

        self.setup_books_frame()
        self.setup_hierarchy_frame()

    def setup_books_frame(self):
        """设置课本部分"""
        # 上半部分：多选框的frame（滚动条）
        self.checkbox_frame = ttk.Frame(self.books_frame)
        self.checkbox_frame.pack(fill=tk.BOTH, expand=True)

        # 创建Canvas和Scrollbar
        self.canvas = tk.Canvas(self.checkbox_frame, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(
            self.checkbox_frame, orient="vertical", command=self.canvas.yview
        )
        self.scrollable_frame = ttk.Frame(self.canvas)

        # 绑定Canvas和Scrollbar
        self.scrollable_frame.bind(
            "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((self.padx, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # 设置最大高度
        self.checkbox_frame.configure(height=self.checkbox_height)  # 设置最大高度
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # 绑定鼠标滚轮事件
        self.canvas.bind_all("<MouseWheel>", self.on_mouse_wheel)
        # 下半部分：全选和取消全选按钮
        btn_frame = ttk.Frame(self.books_frame)
        btn_frame.pack(side=tk.BOTTOM, padx=self.padx)

        self.select_all_btn = ttk.Button(btn_frame, text="全选", command=self.select_all)
        self.deselect_all_btn = ttk.Button(btn_frame, text="取消全选", command=self.deselect_all)
        self.select_all_btn.pack(side=tk.RIGHT)
        self.deselect_all_btn.pack(side=tk.RIGHT)
        self.select_all_btn.config(state=tk.DISABLED)
        self.deselect_all_btn.config(state=tk.DISABLED)

    def setup_hierarchy_frame(self):
        """设置教材层级部分"""
        # 上半部分：下拉框的frame
        self.combo_frame = ttk.Frame(self.hierarchy_frame)
        self.combo_frame.pack(fill=tk.BOTH)  # , expand=True

        # 下半部分：查询按钮
        query_btn_frame = ttk.Frame(self.hierarchy_frame)
        query_btn_frame.pack(side=tk.BOTTOM, anchor="se", padx=self.padx, pady=self.pady)

        self.query_btn = ttk.Button(query_btn_frame, text="查询", command=self.query_data)
        self.query_btn.pack(side=tk.RIGHT)

    def query_data(self):
        """查询数据并更新下拉框"""
        # 这里可以添加查询逻辑
        # messagebox.showinfo("查询", "查询数据并更新下拉框的逻辑")
        # 获取第一级数据
        if self.hier_dict is None:
            self.hierarchy_frame.config(text="联网查询教材数据中……")
            data_dir = None
            self.hier_dict, self.tag_dict, self.id_dict = fetch_metadata(data_dir)

        if self.hier_dict:
            logging.debug(f"hier_dict = {len(self.hier_dict)}")
            self.hierarchy_frame.config(text="查询完成")
            self.hierarchy_frame.config(text=self.frame_names[1])
            self.update_frame(0)
        else:
            self.update_frame(-1, -1)
            messagebox.showerror("错误", "获取数据失败，请稍后再试")

    def update_frame(self, index):
        """更新层级和课本"""
        self._destroy_combobox(index)
        self.update_checkbox(None)
        self.level_options = []
        self.level_hiers = []
        if index < 0:
            return

        self.level_hiers = [self.hier_dict]
        self.level_options = [()]
        selected_key = self.hier_dict["next"][0]
        level, name, options = self._query(selected_key)

        # 创建第一个下拉框
        self.create_combobox(0, name, options)

    def create_combobox(self, index, name, options):
        grid_count = 2
        self._destroy_combobox(index + 1)
        self.update_checkbox(None)

        # Create a frame for the combobox to control its width
        frame = ttk.Frame(self.combo_frame)
        frame.grid(row=index // grid_count, column=index % grid_count, padx=self.padx)
        label = ttk.Label(frame, text=f"[{name}]")
        label.pack(fill=tk.X, side=tk.TOP, expand=True)  # 设置水平居中
        option_names = [op[1] for op in options]
        cb = ttk.Combobox(frame, state="readonly", values=option_names)
        cb.pack(fill=tk.X, expand=True)
        cb.bind("<<ComboboxSelected>>", lambda e: self.on_combobox_select(index, cb.get()))
        self.combobox_list.append([label, cb, frame])

    def on_combobox_select(self, index: int, value: str):
        """处理选事件"""
        logging.debug(f"on_combobox_select index={index}, value={value}")
        self._destroy_combobox(index + 1)
        self.update_checkbox(None)

        # 查找选中项对应的key
        selected_key = None
        current_options = self.level_options[-1]
        for key, name in current_options:
            if name == value:
                selected_key = key
                break
        logging.debug(f"selected_key = {selected_key}, current_options = {current_options}")

        if selected_key:
            level, name, options = self._query(selected_key)
            # 创建多选框或者，下一级下拉框
            if level == -1:
                self.update_checkbox(options)
            else:
                self.create_combobox(index + 1, name, options)

    def _query(self, key):
        # 查询下一个下拉框数据
        current_hier_dict = self.level_hiers[-1]
        level, name, options = query_metadata(key, current_hier_dict, self.tag_dict, self.id_dict)
        self.level_hiers.append(current_hier_dict[key])
        self.level_options.append(options)
        return level, name, options

    def _destroy_combobox(self, index):
        index2 = max(index, 0)
        # 清除现有的下拉框和多选框
        for widgets in self.combobox_list[index2:]:
            for w in widgets:
                w.destroy()
        self.combobox_list = self.combobox_list[:index2]

        self.level_hiers = self.level_hiers[: index2 + 1]
        self.level_options = self.level_options[: index2 + 1]

    def update_checkbox(self, options):
        # 示例多选框
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        self.checkbox_list = []
        self.selected_items = set()
        if options is None:
            self.select_all_btn.config(state=tk.DISABLED)
            self.deselect_all_btn.config(state=tk.DISABLED)
            self.books_frame.config(text=self.frame_names[0])
            return

        for i, (book_id, book_name) in enumerate(options):
            var = tk.BooleanVar()
            cb = ttk.Checkbutton(
                self.scrollable_frame,
                variable=var,
                command=lambda id=book_id: self.toggle_checkbox_selection(id),
            )
            # 使用label自动换行
            label = ttk.Label(self.scrollable_frame, text=book_name, wraplength=self.wraplength)
            cb.grid(row=i, column=0, sticky="w", padx=self.padx * 2, pady=self.pady)
            label.grid(row=i, column=1, sticky="w")
            self.checkbox_list.append((var, cb, label))

        if self.checkbox_list:
            self.select_all_btn.config(state=tk.NORMAL)
            self.deselect_all_btn.config(state=tk.NORMAL)

    def toggle_checkbox_selection(self, book_id: str):
        """切换选择状态"""
        if book_id in self.selected_items:
            self.selected_items.remove(book_id)
        else:
            self.selected_items.add(book_id)
        n1 = len(self.level_options[-1])
        n2 = len(self.selected_items)
        self.books_frame.config(text=f"{self.frame_names[0]}: 共 {n1} 项资源，已选 {n2} 项")

    def select_all(self):
        """全选"""
        self.selected_items = set([op[0] for op in self.level_options[-1]])
        for var in self.checkbox_list:
            var[0].set(True)
        n1 = len(self.level_options[-1])
        n2 = len(self.selected_items)
        self.books_frame.config(text=f"{self.frame_names[0]}: 共 {n1} 项资源，已选 {n2} 项")

    def deselect_all(self):
        """取消全选"""
        self.selected_items = set()
        for var in self.checkbox_list:
            var[0].set(False)
        n1 = len(self.level_options[-1])
        n2 = len(self.selected_items)
        self.books_frame.config(text=f"{self.frame_names[0]}: 共 {n1} 项资源，已选 {n2} 项")

    def get_selected_urls(self) -> list[str]:
        """获取选中的URL列表"""
        return gen_url_from_tags(list(self.selected_items))

    def on_mouse_wheel(self, event):
        """处理鼠标滚轮事件"""
        # 向上滚动
        if event.delta > 0:
            self.canvas.yview_scroll(-1, "units")
        # 向下滚动
        else:
            self.canvas.yview_scroll(1, "units")


class InputURLAreaFrame(ttk.Frame):
    """手动输入面板"""

    def __init__(self, parent, scale=1.0):
        super().__init__(parent)
        self.wraplength = int(500 * scale)
        self.padx = int(5 * scale)
        self.pady = int(5 * scale)
        self.setup_ui()

    def setup_ui(self):
        """初始化UI"""

        # 创建输入区域
        input_frame = ttk.LabelFrame(self, text="输入URL（每行一个）", padding=self.padx * 2)
        input_frame.pack(fill=tk.BOTH, expand=True, padx=self.padx, pady=self.pady)

        # 创建文本框和滚动条
        text_frame = ttk.Frame(input_frame)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=self.pady)
        # TODO 显示行号

        # 添加清空按钮
        btn_frame = ttk.Frame(input_frame)
        btn_frame.pack(fill=tk.X, pady=self.pady)
        clean_btn = ttk.Button(
            btn_frame, text="清空", command=lambda: self.text.delete("1.0", tk.END)
        )
        clean_btn.pack(side=tk.RIGHT)

        self.text = tk.Text(text_frame, height=15)
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)

        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 创建说明区域
        help_frame = ttk.LabelFrame(self, text="格式说明", padding=self.padx * 2)
        help_frame.pack(fill=tk.BOTH, padx=self.padx, pady=self.pady)

        keys = ["/tchMaterial", "/syncClassroom"]
        texts = ""
        for i, key in enumerate(keys, 1):
            config = RESOURCE_DICT[key]
            texts += f"{i}. {config['name'][:2]}URL：" + str(config["resources"]["detail"]) + "\n"

        help_text = f"支持的URL格式示例：\n{texts}\n可以直接从浏览器地址复制URL。"
        help_label = ttk.Label(
            help_frame, text=help_text, wraplength=self.wraplength, justify=tk.LEFT
        )
        help_label.pack(fill=tk.X, padx=self.padx, pady=self.pady)

    def get_urls(self) -> list:
        """获取输入的URL列表"""
        text = self.text.get("1.0", tk.END).strip()
        urls = [url.strip() for url in text.split("\n") if url.strip()] if text else []
        return urls


class DownloadApp(tk.Tk):
    """主应用窗口"""

    def __init__(self, scale=1.0, os_name=None):
        super().__init__()
        self.frame_names = ["books", "inputs"]
        self.frame_titles = ["教材列表", "手动输入"]
        self.desc_texts = DESCRIBES
        
        self.download_dir = DEFAULT_PATH

        self.scale = scale
        width = int(600 * scale)
        height = int(850 * scale)
        self.wraplength = int(500 * scale)
        self.padx = int(5 * scale)
        self.pady = int(5 * scale)
        self.font_size = 12
        if os_name == "Windows":
            self.font_size = int(self.font_size / scale * 1.5)
        logging.info(f"scale = {scale}, width = {width}, height={height}")

        # 图形大小
        self.title(self.desc_texts[0])
        self.geometry(f"{width}x{height}")
        # self.resizable(False, False)  # Prevent resizing the window

        # 设置主题
        # style = ttk.Style()
        # style.theme_use('')

        # 设置Icon
        small_icon_file = base64_to_image(ICON_SMALL, "icon_small.png")
        large_icon_file = base64_to_image(ICON_LARGE, "icon_large.png")
        small_icon = tk.PhotoImage(file=small_icon_file)
        large_icon = tk.PhotoImage(file=large_icon_file)
        self.iconphoto(False, large_icon, small_icon)

        self.setup_ui()

    def setup_ui(self):
        """初始化UI: 标题、目录+下载按钮、单选按钮、内容区域、进度条"""

        main_frame = ttk.Frame(self)  # padding=self.padx*2
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. 添加标题和LOGO
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X)

        ttk.Label(
            title_frame,
            text=LOGO_TEXT,
            font=get_font(["Monaco", "Courier New"], self.font_size, "bold"),
            anchor="center",
        ).pack(fill=tk.BOTH)
        ttk.Label(title_frame, text=self.desc_texts[1]).pack(pady=self.pady * 2)
        ttk.Label(
            title_frame,
            text=self.desc_texts[2],
            wraplength=self.wraplength,
            font=get_font(["楷体", "Kaiti", "STKaiti"], self.font_size, "normal"),
        ).pack(pady=self.pady)

        # 2. 目录+下载按钮
        download_frame = ttk.Frame(main_frame)
        download_frame.pack(fill=tk.X, pady=self.pady)

        # 目录选择
        dir_frame = ttk.Frame(download_frame)
        dir_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Label(dir_frame, text="保存目录：").pack(side=tk.LEFT)
        self.dir_var = tk.StringVar(value=self.download_dir)
        dir_entry = ttk.Entry(dir_frame, textvariable=self.dir_var)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=self.pady)
        ttk.Button(dir_frame, text="选择目录", command=self.choose_directory).pack(side=tk.LEFT)

        # 下载按钮
        ttk.Button(download_frame, text="开始下载", command=self.start_download).pack(
            side=tk.LEFT, padx=self.padx * 2
        )

        # 3. 模式选择：两个单选按钮
        self.mode_var = tk.StringVar(value=self.frame_names[0])
        mode_frame = ttk.Frame(main_frame)
        mode_frame.pack(fill=tk.X, pady=self.pady)

        radio1 = ttk.Radiobutton(
            mode_frame,
            text=self.frame_titles[0],
            value=self.frame_names[0],
            variable=self.mode_var,
            command=self.switch_mode,
        )
        # .pack(side=tk.LEFT, padx=self.padx*2)

        radio2 = ttk.Radiobutton(
            mode_frame,
            text=self.frame_titles[1],
            value=self.frame_names[1],
            variable=self.mode_var,
            command=self.switch_mode,
        )
        # .pack(side=tk.LEFT, padx=self.padx*2)
        radio1.grid(row=0, column=0, sticky="w", padx=self.padx * 2, pady=self.pady)
        radio2.grid(row=0, column=1, sticky="w", padx=self.padx * 2, pady=self.pady)

        # 4. 内容区域，包括两个面板，单选控制
        self.content_frame = ttk.Frame(main_frame)
        self.content_frame.pack(fill=tk.BOTH, expand=True)
        self.selector_frame = BookSelectorFrame(self.content_frame, self.scale)
        self.inputs_frame = InputURLAreaFrame(self.content_frame, self.scale)

        # 默认显示教材列表面板
        self.selector_frame.pack(fill=tk.BOTH, expand=True, pady=self.pady * 2)

        # 底部添加进度条区域
        self.progress_frame = ttk.Frame(main_frame)
        self.progress_frame.pack(fill=tk.X, pady=self.pady)

        # 5. 进度条和标签
        self.progress_var = tk.DoubleVar()
        self.progress_label = ttk.Label(self.progress_frame, text="暂无下载内容")
        self.progress_label.pack(fill=tk.X, pady=self.pady)

        self.progress_bar = ttk.Progressbar(
            self.progress_frame, mode="determinate", variable=self.progress_var
        )
        self.progress_bar.pack(fill=tk.X, pady=self.pady)

        # 默认隐藏进度条区域
        # self.progress_frame.pack_forget()

    def choose_directory(self):
        """选择保存目录"""
        directory = filedialog.askdirectory(title="选择保存目录", initialdir=self.dir_var.get())
        if directory:
            self.dir_var.set(directory)

    def switch_mode(self):
        """切换模式"""
        if self.mode_var.get() == self.frame_names[0]:
            self.inputs_frame.pack_forget()
            self.selector_frame.pack(fill=tk.BOTH, expand=True)
        else:
            self.selector_frame.pack_forget()
            self.inputs_frame.pack(fill=tk.BOTH, expand=True)
            self.inputs_frame.text.focus_set()  # 聚焦在输入框

    def start_download(self):
        """开始下载"""
        # 获取URL列表
        if self.mode_var.get() == self.frame_names[0]:
            urls = self.selector_frame.get_selected_urls()
        else:
            urls = self.inputs_frame.get_urls()

        if not urls:
            messagebox.showwarning("警告", "请先选择或输入要下载的资源")
            return

        # 确认下载弹窗
        # save_dir = self.dir_var.get()
        # if not messagebox.askyesno("确认下载", f"将下载 {len(urls)} 个资源到目录：\n{save_dir}\n\n是否继续？"):
        #     return

        try:
            # 显示进度条
            self.progress_var.set(0)
            self.progress_label.config(text="准备开始下载...")
            self.update()
            result, elapsed_time = self.simple_download(urls)
            self.progress_label.config(text="下载完成。")

            if result:
                message = display_results(result, elapsed_time)
            else:
                message = "下载列表为空"
            messagebox.showinfo("下载结果", message)

        except Exception as e:
            messagebox.showerror("错误", f"下载失败：{str(e)}")

    def simple_download(self, urls, audio=False):
        def _extract_resource_url(data):
            suffix_list = ["pdf"]
            if audio:
                suffix_list.extend(["mp3"])
            return extract_resource_url(data, suffix_list)

        save_path = self.dir_var.get()
        logging.debug(f"\n共选择 {len(urls)} 项目，将保存到 {save_path} 目录，")

        # 更新进度显示
        self.progress_label.config(text="正在解析URL...")
        base_progress = 10
        self.progress_var.set(base_progress)
        self.update()

        config_urls = parse_urls(urls, audio)
        resource_dict = fetch_all_data(config_urls, _extract_resource_url)
        total = len(resource_dict)
        self.progress_label.config(text=f"共找到配置 {len(config_urls)} 项，资源文件 {total} 项")
        base_progress = 20
        self.progress_var.set(base_progress)
        self.update()

        if total == 0:
            logging.warning("\n没有找到资源文件（PDF/MP3等）。结束下载")
            return None, None

        # 开始下载
        start_time = time.time()

        # 更新进度显示
        self.progress_label.config(text=f"开始下载 {total} 项资源...")
        self.update()
        results = download_files_tk(self, resource_dict, save_path, base_progress=base_progress)

        # 更新进度显示
        self.progress_var.set(100)
        self.update()

        elapsed_time = time.time() - start_time
        return results, elapsed_time


def set_dpi_scale():
    import ctypes
    import platform

    scale = 1.0
    os_name = platform.system()
    if os_name == "Windows":
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        ScaleFactor = ctypes.windll.shcore.GetScaleFactorForDevice(0)
        scale = ScaleFactor / 100.0
    return scale, os_name


def main():
    scale, os_name = set_dpi_scale()
    app = DownloadApp(scale, os_name)
    app.eval("tk::PlaceWindow . center")
    app.mainloop()


if __name__ == "__main__":
    # 配置日志
    fmt = "%(asctime)s %(filename)s [line:%(lineno)d] %(levelname)s %(message)s"
    log_level = logging.INFO
    if any(arg in sys.argv[1:] for arg in ["--debug"]):
        log_level = logging.DEBUG
    logging.basicConfig(level=log_level, format=fmt)
    logging.debug("调试模式已启用")

    main()
