import os
import torch
import folder_paths

def is_relative_to(path, base):
    path = os.path.normcase(os.path.realpath(path))
    base = os.path.normcase(os.path.realpath(base))
    return os.path.commonpath([path, base]) == base


def list_all_latents_in_output():
    """
    output 폴더 내의 모든 하위 폴더를 포함하여 .pt 파일을 찾습니다.
    반환값은 output 폴더 기준의 상대 경로(확장자 제외)입니다.
    """
    output_dir = folder_paths.get_output_directory()
    if not os.path.exists(output_dir):
        return []

    latents = []
    # output 폴더 내 모든 파일 탐색
    for root, _, files in os.walk(output_dir):
        for file in files:
            if file.lower().endswith(".pt"):
                full_path = os.path.join(root, file)
                if not is_relative_to(full_path, output_dir):
                    continue
                # output 폴더 기준 상대 경로 생성
                rel_path = os.path.relpath(full_path, output_dir)
                # 확장자 제거
                name_without_ext = os.path.splitext(rel_path)[0]
                # 윈도우 경로(\)를 일관성을 위해 /로 변환 (선택사항이나 보기 좋게)
                latents.append(name_without_ext.replace("\\", "/"))
    
    return sorted(latents)


class A1_Save_Latent:
    """
    LATENT를 output/Saved_Latent (또는 지정한 폴더)에 저장
    output 폴더 외부로는 저장할 수 없도록 제한함
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "samples": ("LATENT",),
                "filename_prefix": ("STRING", {
                    "default": "latent",
                    "tooltip": "저장할 파일 이름 (확장자 불필요)"
                }),
                "folder_name": ("STRING", {
                    "default": "Saved_Latent",
                    "tooltip": "output 폴더 내에 생성할 하위 폴더 이름. output 폴더를 벗어날 수 없습니다."
                }),
            }
        }

    RETURN_TYPES = ()
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = "A1_latent_saver"

    def save(self, samples, filename_prefix, folder_name="Saved_Latent"):
        output_dir = folder_paths.get_output_directory()
        
        # 폴더 이름 공백 제거 및 경로 정리
        folder_name = folder_name.strip()
        filename_prefix = filename_prefix.strip()

        # 경로 조작 방지
        if os.path.isabs(folder_name) or os.path.isabs(filename_prefix):
             # 보안을 위해 강제로 Saved_Latent로 리셋하거나 에러 발생. 여기서는 안전한 경로로 저장되게 처리.
             print(f"[A1_Save_Latent] Invalid folder name detected, reverting to default.")
             folder_name = "Saved_Latent"
             filename_prefix = os.path.basename(filename_prefix)

        save_dir = os.path.join(output_dir, folder_name)

        if not is_relative_to(save_dir, output_dir):
             raise PermissionError("Cannot save outside the output directory.")

        # 확장자(.pt) 중복 입력 방지
        if filename_prefix.lower().endswith(".pt"):
            filename_prefix = filename_prefix[:-3].strip()

        filename = f"{filename_prefix}.pt"
        save_path = os.path.join(save_dir, filename)

        # output 폴더 내부에 있는지 최종 확인 (Symbolic link 등을 통한 탈출 방지)
        if not is_relative_to(save_path, output_dir):
             raise PermissionError("Cannot save outside the output directory.")

        os.makedirs(save_dir, exist_ok=True)

        counter = 1
        # 중복된 파일명이 존재하면 숫자를 붙여서 새로운 이름 생성
        while os.path.exists(save_path):
            filename = f"{filename_prefix}_{counter:02d}.pt"
            save_path = os.path.join(save_dir, filename)
            counter += 1

        # 데이터 준비
        output = {}
        for k, v in samples.items():
            if isinstance(v, torch.Tensor):
                output[k] = v.cpu()
            else:
                output[k] = v
        
        torch.save(output, save_path)

        # 사용자 요청: 주소를 output/saved_latent 처럼 보이게 출력 (상대 경로로 출력)
        rel_path_to_show = os.path.relpath(save_path, output_dir)
        print(f"[A1_Save_Latent] Saved Latent → output/{rel_path_to_show}")

        return ()


class A1_Load_Latent:
    """
    output 폴더 내의 모든 LATENT(.pt) 파일을 찾아서 불러옴
    하위 폴더에 있는 파일도 선택 가능
    """

    @classmethod
    def INPUT_TYPES(cls):
        # 실행 시점에 파일 목록을 갱신하기 위해 동적 리스트 반환이 필요할 수 있음.
        # ComfyUI에서는 INPUT_TYPES가 노드 로딩시 호출되므로 새로고침하려면 웹페이지 새로고침 필요.
        return {
            "required": {
                "name": (
                    list_all_latents_in_output(),
                    {
                        "tooltip": "불러올 latent 파일 선택 (output 폴더 내 검색)"
                    }
                ),
            }
        }

    RETURN_TYPES = ("LATENT",)
    RETURN_NAMES = ("samples",)
    FUNCTION = "load"
    CATEGORY = "A1_latent_saver"

    def load(self, name):
        output_dir = folder_paths.get_output_directory()
        
        # 사용자가 선택한 이름(상대경로)에 .pt 붙이기
        # 만약 리스트 생성시 이미 .pt를 떼고 상대경로(예: Saved_Latent/my_file)를 줬다면
        # 여기서 .pt만 붙이면 됨.
        filename = f"{name}.pt"
        load_path = os.path.join(output_dir, filename)

        if not is_relative_to(load_path, output_dir):
            raise PermissionError("Cannot load outside the output directory.")

        if not os.path.exists(load_path):
             # 윈도우/리눅스 경로 구분자 차이 등으로 못 찾을 경우를 대비해 normalize 시도
             load_path = os.path.normpath(load_path)
             if not os.path.exists(load_path):
                raise FileNotFoundError(
                    f"[A1_Load_Latent] latent not found: {load_path}"
                )

        try:
            data = torch.load(load_path, map_location="cpu", weights_only=True)
        except TypeError:
            data = torch.load(load_path, map_location="cpu")

        if isinstance(data, dict):
            samples = data
        else:
            samples = {"samples": data}

        rel_path_to_show = os.path.relpath(load_path, output_dir)
        print(f"[A1_Load_Latent] Loaded Latent ← output/{rel_path_to_show}")

        return (samples,)
