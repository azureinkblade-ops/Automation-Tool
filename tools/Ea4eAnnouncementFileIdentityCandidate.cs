// Source-only FILE_ID_INFO observation on a caller-owned retained file handle.
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

internal static class Ea4eAnnouncementFileIdentityCandidate
{
    private const int FileIdInfo = 0x12;

    [StructLayout(LayoutKind.Sequential)]
    private struct FileIdentityInfo
    {
        internal ulong VolumeSerialNumber;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 16)]
        internal byte[] FileId;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandleEx(
        SafeFileHandle handle, int infoClass, out FileIdentityInfo info,
        uint size);

    internal static int RequestedInfoClass() { return FileIdInfo; }

    internal static string Screen(ulong volume, byte[] fileId,
                                  out string volumeHex, out string fileIdHex)
    {
        volumeHex = null;
        fileIdHex = null;
        if (volume == 0 || fileId == null || fileId.Length != 16)
            return "DENY:FILE_ID_SHAPE";
        bool nonzero = false;
        char[] hex = new char[32];
        const string digits = "0123456789abcdef";
        for (int i = 0; i < fileId.Length; i++)
        {
            byte value = fileId[i];
            if (value != 0) nonzero = true;
            hex[i * 2] = digits[value >> 4];
            hex[i * 2 + 1] = digits[value & 15];
        }
        if (!nonzero) return "DENY:FILE_ID_ZERO";
        volumeHex = volume.ToString("x16");
        fileIdHex = new string(hex);
        return "CANDIDATE:FILE_ID_ONLY";
    }

    // Caller owns the handle and must bind this observation to the ceremony.
    internal static string Read(SafeFileHandle handle,
                                out string volumeHex, out string fileIdHex)
    {
        volumeHex = null;
        fileIdHex = null;
        if (handle == null || handle.IsInvalid || handle.IsClosed)
            return "DENY:INVALID_HANDLE";
        FileIdentityInfo info;
        if (!GetFileInformationByHandleEx(handle, FileIdInfo, out info,
            (uint)Marshal.SizeOf(typeof(FileIdentityInfo))))
            return "DENY:FILE_ID_UNAVAILABLE";
        return Screen(info.VolumeSerialNumber, info.FileId,
                      out volumeHex, out fileIdHex);
    }
}
