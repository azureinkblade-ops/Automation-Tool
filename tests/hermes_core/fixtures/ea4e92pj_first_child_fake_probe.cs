using System;

internal sealed class FakeHandle : IDisposable
{
    internal bool Closed;
    internal bool ThrowOnDispose;
    public void Dispose()
    {
        Closed = true;
        if (ThrowOnDispose) throw new InvalidOperationException();
    }
}

internal sealed class FakePort : IEa4eDirectoryFirstChildPort
{
    internal string Mode;
    internal int ParentCalls;
    internal int CreateCalls;
    internal int ScreenCalls;
    internal FakeHandle Handle;
    internal bool ExactArguments;

    public string ScreenParent(string path)
    {
        ParentCalls++;
        if (Mode == "parent") return "PARENT_MISMATCH";
        if (Mode == "throw-parent") throw new InvalidOperationException();
        return null;
    }

    public string Create(string path, string sddl, uint access, uint share,
                         uint flags, out IDisposable handle)
    {
        CreateCalls++;
        ExactArguments = path == @"C:\ProgramData\Hermes" &&
            sddl.Contains("0x000200a1") && access == 0x012200a1 &&
            share == 3 && flags == 1;
        Handle = new FakeHandle();
        Handle.ThrowOnDispose = Mode == "throw-dispose";
        handle = Handle;
        if (Mode == "collision") return "ALREADY_EXISTS";
        if (Mode == "missing-handle") { handle = null; return null; }
        if (Mode == "throw-create") throw new InvalidOperationException();
        return null;
    }

    public string ScreenCreated(IDisposable handle, string path, string sddl)
    {
        ScreenCalls++;
        if (Mode == "readback") return "DESCRIPTOR_MISMATCH";
        if (Mode == "throw-screen") throw new InvalidOperationException();
        return null;
    }
}

internal static class Ea4e92pjFirstChildFakeProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        bool retain = args[0].StartsWith("retain-", StringComparison.Ordinal);
        var port = new FakePort { Mode = retain ? args[0].Substring(7) : args[0] };
        IDisposable retained = null;
        string result = retain
            ? Ea4eDirectoryFirstChildCandidate.AttemptAndRetain(
                @"C:\ProgramData",
                @"C:\ProgramData\Hermes\EA4E\IssuerAnnouncements\v1",
                "S-1-5-21-100-200-300-1001", port, out retained)
            : Ea4eDirectoryFirstChildCandidate.Attempt(
                @"C:\ProgramData",
                @"C:\ProgramData\Hermes\EA4E\IssuerAnnouncements\v1",
                "S-1-5-21-100-200-300-1001", port);
        Console.WriteLine(result);
        Console.WriteLine(port.ParentCalls + ":" + port.CreateCalls + ":" +
                          port.ScreenCalls + ":" + port.ExactArguments + ":" +
                          (port.Handle != null && port.Handle.Closed));
        if (retain)
        {
            Console.WriteLine(retained != null);
            if (retained != null) retained.Dispose();
            Console.WriteLine(port.Handle != null && port.Handle.Closed);
        }
        return 0;
    }
}
