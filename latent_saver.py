import os
import torch
import folder_paths

def is_relative_to(path, base):
    path = os.path.normcase(os.path.realpath(path))
    base = os.path.normcase(os.path.realpath(base))
    return os.path.commonpath([path, base]) == base


def list_all_latents_in_output():
    """
    Find all .pt files recursively within the ComfyUI output directory.
    Return paths relative to the output directory without file extensions.
    """
    output_dir = folder_paths.get_output_directory()
    if not os.path.exists(output_dir):
        return []

    latents = []
    # Scan all files under the output directory.
    for root, _, files in os.walk(output_dir):
        for file in files:
            if file.lower().endswith(".pt"):
                full_path = os.path.join(root, file)
                if not is_relative_to(full_path, output_dir):
                    continue
                # Build a path relative to the output directory.
                rel_path = os.path.relpath(full_path, output_dir)
                # Remove the file extension.
                name_without_ext = os.path.splitext(rel_path)[0]
                # Normalize Windows separators for consistent display.
                latents.append(name_without_ext.replace("\\", "/"))
    
    return sorted(latents)


class A1_Save_Latent:
    """
    Save LATENT data to output/Saved_Latent or another specified subfolder.
    Prevent saving files outside the ComfyUI output directory.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "samples": ("LATENT",),
                "filename_prefix": ("STRING", {
                    "default": "latent",
                    "tooltip": "File name for the saved latent (extension is added automatically)."
                }),
                "folder_name": ("STRING", {
                    "default": "Saved_Latent",
                    "tooltip": "Subfolder to create inside the ComfyUI output directory. Saving outside the output directory is not allowed."
                }),
            }
        }

    RETURN_TYPES = ()
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = "A1_latent_saver"

    def save(self, samples, filename_prefix, folder_name="Saved_Latent"):
        output_dir = folder_paths.get_output_directory()
        
        # Trim whitespace from user-provided names.
        folder_name = folder_name.strip()
        filename_prefix = filename_prefix.strip()

        # Prevent absolute-path injection.
        if os.path.isabs(folder_name) or os.path.isabs(filename_prefix):
             # Fall back to a safe folder and strip directories from the file name.
             print(f"[A1_Save_Latent] Invalid folder name detected, reverting to default.")
             folder_name = "Saved_Latent"
             filename_prefix = os.path.basename(filename_prefix)

        save_dir = os.path.join(output_dir, folder_name)

        if not is_relative_to(save_dir, output_dir):
             raise PermissionError("Cannot save outside the output directory.")

        # Prevent duplicate .pt extensions.
        if filename_prefix.lower().endswith(".pt"):
            filename_prefix = filename_prefix[:-3].strip()

        filename = f"{filename_prefix}.pt"
        save_path = os.path.join(save_dir, filename)

        # Verify that the final path remains inside the output directory.
        if not is_relative_to(save_path, output_dir):
             raise PermissionError("Cannot save outside the output directory.")

        os.makedirs(save_dir, exist_ok=True)

        counter = 1
        # Add a numeric suffix when a file with the same name already exists.
        while os.path.exists(save_path):
            filename = f"{filename_prefix}_{counter:02d}.pt"
            save_path = os.path.join(save_dir, filename)
            counter += 1

        # Move tensors to the CPU before saving.
        output = {}
        for k, v in samples.items():
            if isinstance(v, torch.Tensor):
                output[k] = v.cpu()
            else:
                output[k] = v
        
        torch.save(output, save_path)

        # Display the saved location as a path relative to the output directory.
        rel_path_to_show = os.path.relpath(save_path, output_dir)
        print(f"[A1_Save_Latent] Saved latent to output/{rel_path_to_show}")

        return ()


class A1_Load_Latent:
    """
    Find and load LATENT (.pt) files from the ComfyUI output directory.
    Files in nested subfolders can also be selected.
    """

    @classmethod
    def INPUT_TYPES(cls):
        # Build the file list when ComfyUI requests the node input schema.
        # Refresh the ComfyUI page to update the list after files change.
        return {
            "required": {
                "name": (
                    list_all_latents_in_output(),
                    {
                        "tooltip": "Select a latent file to load from the ComfyUI output directory."
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
        
        # Append .pt to the selected relative path.
        # The selection list stores paths without the .pt extension,
        # for example: Saved_Latent/my_file.
        filename = f"{name}.pt"
        load_path = os.path.join(output_dir, filename)

        if not is_relative_to(load_path, output_dir):
            raise PermissionError("Cannot load outside the output directory.")

        if not os.path.exists(load_path):
             # Normalize the path to handle platform-specific separators.
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
        print(f"[A1_Load_Latent] Loaded latent from output/{rel_path_to_show}")

        return (samples,)
