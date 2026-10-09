# PhotoPicker capture-date and export fix

Nested camera EXIF timestamps now reach gallery manifests, and saved JPEG/WebP/full-size/thumbnail exports retain EXIF. Originals are unchanged. A real1001-byte HEIF regression fixture is included; it contains only a generated blue rectangle and synthetic camera/date metadata. No inference/download is required.

Before the fix:11new assertions failed and1passed. Afterward:80distinct focused tests passed, with no skips/failures. Pinned Ruff0.15.20 passes. Four actual exported images decode and retain the date; the actual PhotoPick manifest includes the date, dimensions and all export references. The synthetic source HEIF is byte-identical. Runtime: installedPython3.10.11/Pillow12.3.0/pillow-heif1.4.0.

Usable output images and GALLERY_MANIFEST.json are saved in the fleet photopicker/metadata-qualification directory. Product patch and reproducible tests are in this repository. TASK_RETURN.json records exact source hashes and remaining owners/gates; JOINT_ACCEPTANCE.json keeps separate Michael/agent observations.

CHECKPOINTED: remaining profile/culler/UI/packaging qualification continues locally. Main integration, exact release artifact, actual private-photo acceptance and optional models remain gated. No publication, install, provider call or real photo was used.

Native runtime limitation: an untracked `%SystemDrive%/ProgramData/Microsoft/Windows/Caches` directory was observed after the commit. Only filenames/sizes were inspected; contents remain unread and unstaged. Python audit controls are not native/OS I/O confinement. Tracked project files are clean; the whole worktree contains this preserved cache.
