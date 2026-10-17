// Read-only path-topology observation. A match is not an ACL or issuer witness.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

internal static class Ea4eProtectedPathTopologyCandidate
{
    private const uint ReadControl = 0x00020000;
    private const uint ReadAttributes = 0x00000080;
    private const uint ShareAll = 0x00000007;
    private const uint OpenExisting = 3;
    private const uint BackupSemantics = 0x02000000;
    private const uint OpenReparsePoint = 0x00200000;
    private const uint DirectoryAttribute = 0x00000010;
    private const uint ReparseAttribute = 0x00000400;

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

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true,
        EntryPoint = "CreateFileW")]
    private static extern SafeFileHandle CreateFile(
        string path, uint access, uint share, IntPtr securityAttributes,
        uint disposition, uint flags, IntPtr template);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandleEx(
        SafeFileHandle handle, int infoClass, out FileAttributeTagInfo info,
        uint size);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandle(
        SafeFileHandle handle, out ByHandleFileInformation info);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true,
        EntryPoint = "GetFinalPathNameByHandleW")]
    private static extern uint GetFinalPathNameByHandle(
        SafeFileHandle handle, StringBuilder path, uint capacity, uint flags);

    private static string FinalPath(SafeFileHandle handle)
    {
        var buffer = new StringBuilder(32768);
        uint length = GetFinalPathNameByHandle(handle, buffer, (uint)buffer.Capacity, 0);
        if (length == 0 || length >= buffer.Capacity)
            throw new InvalidOperationException("Final path unavailable");
        string value = buffer.ToString();
        if (!value.StartsWith(@"\\?\", StringComparison.Ordinal))
            throw new InvalidOperationException("Unexpected path namespace");
        return value.Substring(4).TrimEnd('\\');
    }

    private static bool SamePath(string first, string second)
    {
        return String.Equals(first.TrimEnd('\\'), second.TrimEnd('\\'),
                             StringComparison.OrdinalIgnoreCase);
    }

    internal static string Denial(string path)
    {
        return Denial(path, null);
    }

    internal static string Denial(string path, Func<SafeFileHandle, string, bool, string> observer)
    {
        return DenialCore(path, observer, false);
    }

    internal static string DenialWithReadableLeaf(
        string path, Func<SafeFileHandle, string, bool, string> observer)
    {
        return DenialCore(path, observer, true);
    }

    private static string DenialCore(
        string path, Func<SafeFileHandle, string, bool, string> observer,
        bool readableLeaf)
    {
        if (String.IsNullOrEmpty(path) || path.Length > 32767
            || path.Length < 4 || !Char.IsLetter(path[0]) || path[1] != ':'
            || path[2] != '\\' || path.IndexOf(':', 2) >= 0
            || path.IndexOf('/') >= 0)
            return "PATH_FORM_DENIED";
        string full;
        try { full = Path.GetFullPath(path); }
        catch { return "PATH_FORM_DENIED"; }
        if (!SamePath(full, path)) return "PATH_NOT_CANONICAL";

        var handles = new List<SafeFileHandle>();
        var names = new List<string>();
        try
        {
            string current = Path.GetPathRoot(full);
            names.Add(current);
            foreach (string component in full.Substring(current.Length).Split('\\'))
            {
                if (component.Length == 0 || component == "." || component == "..")
                    return "PATH_COMPONENT_DENIED";
                current = Path.Combine(current, component);
                names.Add(current);
            }
            if (names.Count < 2) return "TARGET_MISSING";
            for (int index = 0; index < names.Count; index++)
            {
                bool leaf = index == names.Count - 1;
                uint access = ReadControl | ReadAttributes | (leaf && readableLeaf ? 1u : 0u);
                uint share = leaf && readableLeaf ? 1u : ShareAll;
                var handle = CreateFile(names[index], access,
                    share, IntPtr.Zero, OpenExisting,
                    BackupSemantics | OpenReparsePoint, IntPtr.Zero);
                if (handle == null || handle.IsInvalid)
                {
                    if (handle != null) handle.Dispose();
                    return "OPEN_DENIED";
                }
                handles.Add(handle);
                FileAttributeTagInfo tag;
                if (!GetFileInformationByHandleEx(handle, 9, out tag,
                    (uint)Marshal.SizeOf(typeof(FileAttributeTagInfo))))
                    return "ATTRIBUTES_UNAVAILABLE";
                if ((tag.Attributes & ReparseAttribute) != 0)
                    return "REPARSE_DENIED";
                bool directory = (tag.Attributes & DirectoryAttribute) != 0;
                if (directory != (index < names.Count - 1))
                    return "OBJECT_TYPE_DENIED";
                ByHandleFileInformation identity;
                if (!GetFileInformationByHandle(handle, out identity))
                    return "IDENTITY_UNAVAILABLE";
                if (index == names.Count - 1 && identity.LinkCount != 1)
                    return "MULTILINK_DENIED";
                if (!SamePath(FinalPath(handle), names[index]))
                    return "PATH_SUBSTITUTION_DENIED";
            }
            for (int index = 0; index < handles.Count; index++)
                if (!SamePath(FinalPath(handles[index]), names[index]))
                    return "PATH_SUBSTITUTION_DENIED";
            if (observer != null)
            {
                for (int index = handles.Count - 1; index >= 0; index--)
                {
                    string denial = observer(handles[index], names[index],
                                             index < handles.Count - 1);
                    if (denial != null) return denial;
                }
                for (int index = 0; index < handles.Count; index++)
                    if (!SamePath(FinalPath(handles[index]), names[index]))
                        return "PATH_SUBSTITUTION_DENIED";
            }
            return null;
        }
        catch
        {
            return "OBSERVATION_UNAVAILABLE";
        }
        finally
        {
            foreach (var handle in handles) handle.Dispose();
        }
    }
}
