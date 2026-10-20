// Read-only known-folder lookup; the returned path is not a topology witness.
using System;
using System.Runtime.InteropServices;

internal static class Ea4eProgramDataKnownFolderCandidate
{
    private static readonly Guid ProgramDataId = new Guid(
        "62AB5D82-FDC1-4DC3-A9DD-070D1D495D97");

    [DllImport("shell32.dll", ExactSpelling = true)]
    private static extern int SHGetKnownFolderPath(
        ref Guid folderId, uint flags, IntPtr token, out IntPtr path);

    internal static string Resolve(out string path)
    {
        path = null;
        IntPtr pointer = IntPtr.Zero;
        try
        {
            Guid id = ProgramDataId;
            int result = SHGetKnownFolderPath(ref id, 0, IntPtr.Zero, out pointer);
            if (result != 0 || pointer == IntPtr.Zero)
                return "DENY:KNOWN_FOLDER_UNAVAILABLE";
            string value = Marshal.PtrToStringUni(pointer);
            if (String.IsNullOrEmpty(value))
                return "DENY:KNOWN_FOLDER_EMPTY";
            path = value;
            return null;
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            return "DENY:KNOWN_FOLDER_UNAVAILABLE";
        }
        finally
        {
            if (pointer != IntPtr.Zero) Marshal.FreeCoTaskMem(pointer);
        }
    }
}
