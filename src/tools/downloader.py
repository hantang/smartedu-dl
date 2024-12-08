import logging
from concurrent.futures import as_completed, ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import requests

from .utils import gen_filename, get_headers


def download_file(url: str, headers: dict, timeout: int, chunk_size: int, file_path: str | Path):
    """下载单个文件"""

    out = {"url": url, "status": None, "code": -1, "file": str(file_path), "size": -1}
    try:
        with requests.get(url, headers=headers, stream=True, timeout=timeout) as response:
            # response.raise_for_status()
            logging.debug(f"download url = {url}, status = {response.status_code}")
            out["code"] = response.status_code
            if response.ok:
                total_size = int(response.headers.get("content-length", 0))

            with open(file_path, "wb") as file:
                for data in response.iter_content(chunk_size=chunk_size):
                    file.write(data)
                    file.flush()

            if total_size != 0 and Path(file_path).stat().st_size != total_size:
                raise RuntimeError("Could not download file")

            out["size"] = total_size
            out["status"] = "success"
            logging.debug(f"Download success: {url} -> {file_path}")
            return out

    except requests.exceptions.RequestException as res_err:
        logging.warning(f"URL: {url}; Request Error: {res_err}")
    except IOError as io_err:
        logging.warning(f"URL: {url}; IO Error: {io_err}")
    except Exception as err:
        logging.error(f"Download failed: {url}, 错误: {err}")

    out["status"] = "failed"
    return out


def download_file2(url, name, save_dir, raw_url):
    headers = get_headers()
    timeout = 10
    chunk_size = 16 * 1024  # 16k
    file_path = gen_filename(url, name, save_dir)
    out = download_file(url, headers, timeout, chunk_size, file_path)
    out["raw"] = raw_url
    return out


def download_files(url_dict: dict, output_dir: str, max_workers: int = 5) -> list:
    """并发下载多个文件"""
    save_dir = Path(output_dir)
    if not save_dir.exists():
        save_dir.mkdir(parents=True)

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(download_file2, url, name, save_dir, raw_url): url
            for url, [name, raw_url] in url_dict.items()
        }
        for future in as_completed(future_to_url):
            # url = future_to_url[future]
            result = future.result()
            results.append(result)

    return results


def download_files_tk(app, url_dict: dict, output_dir: str, max_workers: int = 5, base_progress: int = 0) -> list:
    """tk下载文件，更新进度条"""
    save_dir = Path(output_dir)
    if not save_dir.exists():
        save_dir.mkdir(parents=True)

    results = []
    total = len(url_dict)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(download_file2, url, name, save_dir, raw_url): url
            for url, [name, raw_url] in url_dict.items()
        }
        for future in as_completed(future_to_url):
            # url = future_to_url[future]
            result = future.result()
            results.append(result)

            finished = len(results)
            app.progress_label.config(text=f"已经下载 {finished} / {total} 项资源...")
            app.progress_var.set(base_progress + (finished / total) * (100-base_progress))
            app.update()

    return results


def fetch_single_data(
    url: str, headers: dict, timeout: int, data_format: str = "json"
) -> list | dict | str | None:
    # 获取json配置
    try:
        response = requests.get(url, timeout=timeout, headers=headers)
        # logging.debug(f"URL = {url}, status = {response.status_code}")
        if response.ok:
            return response.json() if data_format == "json" else response.text
        logging.debug(f"Failed url={url}, status={response.status_code}")
    except requests.exceptions.RequestException as res_err:
        logging.warning(f"URL: {url}; Request Error: {res_err}")
    except IOError as io_err:
        logging.warning(f"URL: {url}; IO Error: {io_err}")
    except Exception as err:
        logging.error(f"Download failed: {url}, 错误: {err}")

    return None


def fetch_all_data(url_list: list, extract_func: Callable, max_workers: int = 5) -> dict:
    """
    获取配置信息
    """
    headers = get_headers()
    timeout = 5
    data_format = "json"

    results = {}
    total = len(url_list)

    # with tqdm(total=total, desc="获取资源链接") as pbar:
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(fetch_single_data, url, headers, timeout, data_format): url
            for url in url_list
        }

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                if result:
                    resource = extract_func(result)
                    for title, resource_url in resource:
                        if resource_url:
                            logging.debug(f"title = {title}, resource_url={resource_url}")
                            results[resource_url] = [title, url]
                else:
                    logging.debug(f"None data URL = {url}")
            except Exception as e:
                logging.error(f"处理URL失败: {url}, 错误: {e}")
            # finally:
            #     pbar.update(1)
            #     # pbar.set_postfix({"找到": len(results)})

    return results
