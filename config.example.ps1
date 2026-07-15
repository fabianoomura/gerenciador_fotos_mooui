$CatalogoConfig = @{
    LinuxProject = "/mnt/c/path/to/visual-photo-catalog"
    LinuxDb = "/home/username/.local/share/visual-photo-catalog/catalog.db"
    LinuxDbDir = "/home/username/.local/share/visual-photo-catalog"
    LinuxPython = "/home/username/.venvs/visual-photo-catalog/bin/python"
    Share = "//fileserver/photo-library"
    MountPoint = "/mnt/photo-library"
    CredentialsFile = "/etc/samba/photo-library.credentials"
    PhotoRoot = "/mnt/photo-library/photos"
    PublicUrl = "http://localhost:7777"
    AllowedDevOrigins = "localhost"
    ApiToken = "replace-with-a-long-random-token"
    Uid = 1000
    Gid = 1000
}
