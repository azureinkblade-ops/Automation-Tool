// Source-only bounded read from a caller-owned handle; not an issuer witness.
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

internal static class Ea4eAnnouncementRetainedReadCandidate
{
    internal const uint MaximumRecordBytes = 1024;
    private const uint DirectoryAttribute = 0x00000010;
    private const uint ReparseAttribute = 0x00000400;
    private const int ErrorHandleEof = 38;

    [StructLayout(LayoutKind.Sequential)]
    private struct FileAttributeTagInfo
    {
        internal uint Attributes;
        internal uint ReparseTag;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct FileTime
    {
        internal uint Low;
        internal uint High;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct ByHandleFileInformation
    {
        internal uint Attributes;
        internal FileTime CreationTime;
        internal FileTime AccessTime;
        internal FileTime WriteTime;
        internal uint VolumeSerial;
        internal uint SizeHigh;
        internal uint SizeLow;
        internal uint LinkCount;
        internal uint FileIndexHigh;
        internal uint FileIndexLow;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandleEx(
        SafeFileHandle handle, int infoClass, out FileAttributeTagInfo info,
        uint size);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandle(
        SafeFileHandle handle, out ByHandleFileInformation info);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetFilePointerEx(
        SafeFileHandle handle, long distance, out long newPosition, uint origin);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ReadFile(
        SafeFileHandle handle, byte[] buffer, uint count,
        out uint read, IntPtr overlapped);

    internal static string ScreenShape(uint attributes, uint links, ulong size)
    {
        if ((attributes & ReparseAttribute) != 0) return "DENY:REPARSE";
        if ((attributes & DirectoryAttribute) != 0) return "DENY:NOT_FILE";
        if (links != 1) return "DENY:MULTILINK";
        if (size == 0 || size > MaximumRecordBytes) return "DENY:SIZE";
        return "CANDIDATE:FILE_SHAPE_ONLY";
    }

    private static ulong Size(ByHandleFileInformation info)
    {
        return ((ulong)info.SizeHigh << 32) | info.SizeLow;
    }

    private static bool Same(ByHandleFileInformation first,
                             ByHandleFileInformation second)
    {
        return first.Attributes == second.Attributes &&
            first.VolumeSerial == second.VolumeSerial &&
            first.FileIndexHigh == second.FileIndexHigh &&
            first.FileIndexLow == second.FileIndexLow &&
            first.LinkCount == second.LinkCount &&
            first.SizeHigh == second.SizeHigh &&
            first.SizeLow == second.SizeLow &&
            first.CreationTime.High == second.CreationTime.High &&
            first.CreationTime.Low == second.CreationTime.Low &&
            first.WriteTime.High == second.WriteTime.High &&
            first.WriteTime.Low == second.WriteTime.Low;
    }

    // Caller retains and closes the exact handle; this method never opens a path.
    internal static string Read(SafeFileHandle handle, out byte[] record)
    {
        record = null;
        if (handle == null || handle.IsInvalid || handle.IsClosed)
            return "DENY:INVALID_HANDLE";
        ByHandleFileInformation before;
        FileAttributeTagInfo tagBefore;
        if (!GetFileInformationByHandle(handle, out before) ||
            !GetFileInformationByHandleEx(handle, 9, out tagBefore,
                (uint)Marshal.SizeOf(typeof(FileAttributeTagInfo))))
            return "DENY:METADATA_UNAVAILABLE";
        if (before.Attributes != tagBefore.Attributes)
            return "DENY:METADATA_DRIFT";
        string shape = ScreenShape(before.Attributes,
                                   before.LinkCount, Size(before));
        if (shape != "CANDIDATE:FILE_SHAPE_ONLY") return shape;
        long position;
        if (!SetFilePointerEx(handle, 0, out position, 0) || position != 0)
            return "DENY:SEEK_UNAVAILABLE";

        int length = checked((int)Size(before));
        byte[] bytes = new byte[length];
        byte[] one = new byte[1];
        for (int index = 0; index <= length; index++)
        {
            uint read;
            bool ok = ReadFile(handle, one, 1, out read, IntPtr.Zero);
            if (index == length)
            {
                if ((!ok && Marshal.GetLastWin32Error() == ErrorHandleEof) ||
                    (ok && read == 0)) break;
                return "DENY:TRAILING_OR_READ_ERROR";
            }
            if (!ok || read != 1) return "DENY:SHORT_OR_READ_ERROR";
            bytes[index] = one[0];
        }

        ByHandleFileInformation after;
        FileAttributeTagInfo tagAfter;
        if (!GetFileInformationByHandle(handle, out after) ||
            !GetFileInformationByHandleEx(handle, 9, out tagAfter,
                (uint)Marshal.SizeOf(typeof(FileAttributeTagInfo))) ||
            !Same(before, after) ||
            tagBefore.Attributes != tagAfter.Attributes ||
            tagBefore.ReparseTag != tagAfter.ReparseTag)
            return "DENY:IDENTITY_DRIFT";
        record = bytes;
        return "CANDIDATE:BYTES_ONLY";
    }
}
