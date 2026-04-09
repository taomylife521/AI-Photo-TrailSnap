import uuid
import json
import numpy as np
import cv2
import logging
import os
from app.config import settings
from app.services.model_manager import model_manager
from app.services.model_downloader import model_downloader
from app.services.ai_config_manager import ai_config_manager
from app.services.ticket_parser import parse_ticket_info, extract_text
from app.services.fly_ticket_parser import extract_flight_info

def load_modelscope_model():
    """
    Downloads the Ticket Recognition model from ModelScope.
    Returns the local directory path of the downloaded model.
    """
    try:
        from modelscope import snapshot_download
        model_name = ai_config_manager.get_model_selection("ticket_recognition")
        if not model_name:
            model_name = "rpxaaa/ticket_recognition"
            
        logging.info(f"Downloading/Verifying Ticket Recognition model ({model_name})...")
        model_dir = os.path.join(settings.MODEL_PATH, 'ticket_recognition')
        
        # Download model using snapshot_download
        path = snapshot_download(model_name, local_dir=model_dir)
        return path
    except Exception as e:
        logging.error(f"Failed to download Ticket Recognition model: {e}")
        raise e

def load_yolo_model():
    """
    Initializes and returns the YOLO model for ticket recognition.
    """
    try:
        from ultralytics import YOLO

        import torch
        logging.info("Initializing YOLO model for Ticket Recognition...")
        
        # Ensure model is downloaded and get path
        model_dir = load_modelscope_model()
        model_path = os.path.join(model_dir, "best.pt")
        
        # Initialize YOLO model
        yolo_model = YOLO(model=model_path)
        
        # Handle device selection similar to InsightFace example logic
        # Check for CUDA availability
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        yolo_model.to(device)
        
        logging.info(f"YOLO model initialized successfully on {device}.")
        return yolo_model
    except Exception as e:
        logging.error(f"Failed to initialize YOLO model: {e}")
        raise e


def release_yolo_model(model):
    del model
    logging.info("YOLO model released")

# 注册 YOLO 模型
model_manager.register_model("tickets_yolo", load_yolo_model, release_yolo_model)

class TicketService:
    def __init__(self):
        self._register_downloads()

    def _register_downloads(self):
        def check_model():
            return False
            model_path = os.path.join(settings.MODEL_PATH, 'ticket_recognition', 'best.pt')
            return os.path.exists(model_path)

        def download_model():
            return load_modelscope_model()

        model_downloader.register_model("tickets_yolo", check_model, download_model)

    def detect(self, image_bytes: bytes):
        """
        执行车票检测与识别
        """
        # Check if model is ready
        # Note: Since load_yolo_model now handles download internally/synchronously if needed,
        # we might not strictly need this check if we relied solely on load_yolo_model.
        # However, keeping it consistent with the model_downloader pattern is good practice.
        if not model_downloader.is_ready("tickets_yolo"):
             # If model_downloader is used, we respect its status.
             # If strictly following the user's synchronous load pattern, this might be redundant but safe.
             # For now, we'll keep it as a fast check.
             if not os.path.exists(os.path.join(settings.MODEL_PATH, 'ticket_recognition', 'best.pt')):
                 raise Exception("Ticket recognition model is not ready yet. Please try again later.")

        # 获取模型实例
        yolo = model_manager.get_model("tickets_yolo")

        # 解码图像
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image data")

        # 查找 'label' (火车票) 和 'label1' (飞机票) 标签的索引
        target_classes = []
        if hasattr(yolo, "names"):
            for idx, name in yolo.names.items():
                if name == "label" or name == "label1":
                    target_classes.append(idx)

        # YOLO 推理
        # save=False, verbose=False 以提高性能
        results = yolo.predict(source=img, save=False, verbose=False, classes=target_classes)

        tickets = []

        # 确保输出目录存在 (用于调试或模拟中间文件)
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        if not results:
            return {"tickets": tickets, "count": 0}

        ocr = None
        filtered_count = 0

        for result in results:
            boxes = getattr(result, "boxes", None)
            orig_img = getattr(result, "orig_img", img)

            if boxes is None:
                continue

            for i, box in enumerate(boxes):
                # 解析YOLO检测结果中的confidence字段
                conf = box.conf[0].item()

                # 实现阈值比较判断（confidence > 0.6）
                if conf <= 0.6:
                    filtered_count += 1
                    continue

                # 获取坐标
                xyxy = box.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = map(int, xyxy)

                # 边界保护
                h, w = orig_img.shape[:2]
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(w, x2)
                y2 = min(h, y2)

                # 裁剪车票区域
                crop = orig_img[y1:y2, x1:x2]
                if crop.size == 0:
                    continue

                # 1. 保存裁剪图像到临时文件
                temp_filename = f"temp_crop_{uuid.uuid4().hex[:8]}_{conf*100:.0f}.png"
                temp_path = os.path.join(output_dir, temp_filename)
                cv2.imwrite(temp_path, crop)

                try:
                    # 2. 对裁剪区域执行 OCR (传入文件路径)
                    # RapidOCR 支持路径输入
                    if not ocr:
                        ocr = model_manager.get_model("ocr")
                    out = ocr(temp_path)
                except Exception as e:
                    logging.warning(f"OCR inference failed for {temp_path}: {e}")
                    out = None
                finally:
                    pass
                    # 清理临时图片文件
                    # if os.path.exists(temp_path):
                    #     os.remove(temp_path)

                if isinstance(out, tuple):
                    ocr_result = out[0]
                else:
                    ocr_result = out
                
                # 构造 JSON 数据结构以模拟 yolo_ocr.py 的中间结果
                json_data = {"rec_texts": [], "rec_polys": []}
                if ocr_result:
                    try:
                        # Check for RapidOCROutput object (has txts, boxes, scores attributes)
                        if hasattr(ocr_result, 'txts') and hasattr(ocr_result, 'boxes'):
                            # Handle RapidOCROutput object
                            txts = ocr_result.txts
                            boxes = ocr_result.boxes
                            for i in range(len(txts)):
                                text = txts[i]
                                # Convert numpy array box to list for JSON serialization
                                poly = boxes[i].tolist() if hasattr(boxes[i], 'tolist') else boxes[i]
                                json_data["rec_texts"].append(str(text))
                                json_data["rec_polys"].append(poly)
                        else:
                            # Handle standard list of tuples/lists
                            for item in ocr_result:
                                if isinstance(item, (list, tuple)) and len(item) >= 2:
                                    poly = item[0]
                                    text = item[1]
                                    json_data["rec_texts"].append(str(text))
                                    json_data["rec_polys"].append(poly)
                    except Exception as e:
                         logging.warning(f"OCR result parse failed: {e}")

                # 3. 保存原始OCR结果到JSON (完全对齐 yolo_ocr.py 流程)
                json_filename = f"temp_crop_{uuid.uuid4().hex[:8]}_ocr.json"
                json_path = os.path.join(output_dir, json_filename)
                try:
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(json_data, f, ensure_ascii=False, indent=2)
                    
                    # 4. 从JSON文件中提取文本 (调用 ticket_parser_adapter 中的 extract_text)
                    texts, polys = extract_text(json_path)
                    
                    # 调试日志：打印 OCR 识别到的文本
                    # logging.info(f"Ticket detection {i}: extracted texts from JSON: {texts}")

                    # 5. 解析车票信息
                    cls_id = int(box.cls[0].item())
                    cls_name = result.names[cls_id]
                    
                    if cls_name == "label1":
                        # 飞机票
                        info = extract_flight_info(texts)
                        info["type"] = "flight"
                    else:
                        # 火车票 (label)
                        info = parse_ticket_info(texts, polys)
                        info["type"] = "train"
                    
                    logging.info(f"Ticket detection {i} ({cls_name}): parsed info: {info}")
                    if info:
                        info['detection_id'] = i
                        tickets.append(info)

                except Exception as e:
                    logging.error(f"Error processing JSON flow for ticket {i}: {e}")
                finally:
                    # 清理临时 JSON 文件
                    if os.path.exists(json_path):
                        os.remove(json_path)

        if filtered_count > 0:
            logging.info(f"Filtered out {filtered_count} low confidence detections")

        return {"tickets": tickets, "count": len(tickets)}

ticket_service = TicketService()
