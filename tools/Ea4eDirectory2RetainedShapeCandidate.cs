// Source-only observation on a caller-owned directory handle; no path open.
using System;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

internal static class Ea4eDirectory2RetainedShapeCandidate
{
    private const uint FileTypeDisk = 1;
    private const uint DirectoryAttribute = 0x10;
    private const uint ReparseAttribute = 0x400;

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
    private static extern uint GetFileType(SafeFileHandle handle);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandle(
        SafeFileHandle handle, out ByHandleFileInformation info);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandleEx(
        SafeFileHandle handle, int infoClass, out FileAttributeTagInfo info,
        uint size);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode,
        EntryPoint = "GetFinalPathNameByHandleW", SetLastError = true)]
    private static extern uint GetFinalPathNameByHandle(
        SafeFileHandle handle, StringBuilder path, uint capacity, uint flags);

    internal static string Screen(uint fileType, uint attributes,
                                  uint tagAttributes, uint links,
                                  string finalPath, string expectedPath)
    {
        if (fileType != FileTypeDisk) return "DENY:FILE_TYPE";
        if (attributes != tagAttributes ||
            (attributes & DirectoryAttribute) == 0 ||
            (attributes & ReparseAttribute) != 0 || links != 1)
            return "DENY:DIRECTORY_SHAPE";
        if (String.IsNullOrEmpty(finalPath) ||
            !finalPath.StartsWith(@"\\?\", StringComparison.Ordinal) ||
            String.IsNullOrEmpty(expectedPath))
            return "DENY:FINAL_PATH_FORM";
        string observed = finalPath.Substring(4);
        if (observed.Length < 4 || !Char.IsLetter(observed[0]) ||
            observed[1] != ':' || observed[2] != '\\' ||
            !String.Equals(observed, expectedPath,
                           StringComparison.OrdinalIgnoreCase))
            return "DENY:FINAL_PATH_MISMATCH";
        return "CANDIDATE:RETAINED_DIRECTORY_SHAPE_ONLY";
    }

    private static bool Same(ByHandleFileInformation a,
                             ByHandleFileInformation b)
    {
        return a.Attributes == b.Attributes &&
            a.VolumeSerial == b.VolumeSerial &&
            a.LinkCount == b.LinkCount &&
            a.FileIndexHigh == b.FileIndexHigh &&
            a.FileIndexLow == b.FileIndexLow &&
            a.SizeHigh == b.SizeHigh && a.SizeLow == b.SizeLow &&
            a.CreationTime.High == b.CreationTime.High &&
            a.CreationTime.Low == b.CreationTime.Low &&
            a.WriteTime.High == b.WriteTime.High &&
            a.WriteTime.Low == b.WriteTime.Low;
    }

    private static string FinalPath(SafeFileHandle handle)
    {
        var path = new StringBuilder(32768);
        uint length = GetFinalPathNameByHandle(
            handle, path, (uint)path.Capacity, 0);
        return length == 0 || length >= path.Capacity ? null : path.ToString();
    }

    // This never opens or closes the supplied handle. The caller owns it.
    internal static string Read(SafeFileHandle handle, string expectedPath,
                                out string volumeHex, out string fileIdHex)
    {
        volumeHex = null;
        fileIdHex = null;
        if (handle == null || handle.IsInvalid || handle.IsClosed)
            return "DENY:INVALID_HANDLE";
        try
        {
            ByHandleFileInformation first, second;
            FileAttributeTagInfo firstTag, secondTag;
            uint fileType = GetFileType(handle);
            if (!GetFileInformationByHandle(handle, out first) ||
                !GetFileInformationByHandleEx(handle, 9, out firstTag,
                    (uint)Marshal.SizeOf(typeof(FileAttributeTagInfo))))
                return "DENY:METADATA_UNAVAILABLE";
            string firstPath = FinalPath(handle);
            string firstVolume, firstId;
            if (Ea4eAnnouncementFileIdentityCandidate.Read(
                    handle, out firstVolume, out firstId) !=
                "CANDIDATE:FILE_ID_ONLY")
                return "DENY:FILE_ID_UNAVAILABLE";
            if (!GetFileInformationByHandle(handle, out second) ||
                !GetFileInformationByHandleEx(handle, 9, out secondTag,
                    (uint)Marshal.SizeOf(typeof(FileAttributeTagInfo))))
                return "DENY:METADATA_UNAVAILABLE";
            string secondPath = FinalPath(handle);
            string secondVolume, secondId;
            if (Ea4eAnnouncementFileIdentityCandidate.Read(
                    handle, out secondVolume, out secondId) !=
                "CANDIDATE:FILE_ID_ONLY" || !Same(first, second) ||
                firstTag.Attributes != secondTag.Attributes ||
                firstTag.ReparseTag != secondTag.ReparseTag ||
                !String.Equals(firstPath, secondPath, StringComparison.Ordinal) ||
                firstVolume != secondVolume || firstId != secondId)
                return "DENY:IDENTITY_DRIFT";
            string result = Screen(fileType, first.Attributes,
                firstTag.Attributes, first.LinkCount, firstPath, expectedPath);
            if (result == "CANDIDATE:RETAINED_DIRECTORY_SHAPE_ONLY")
            {
                volumeHex = firstVolume;
                fileIdHex = firstId;
            }
            return result;
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            return "DENY:OBSERVATION_UNAVAILABLE";
        }
    }
}
