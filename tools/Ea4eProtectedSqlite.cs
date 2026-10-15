// Candidate low-level store dependency. It does not issue or consume authority.
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

internal sealed class Ea4eProtectedSqlite : IDisposable
{
    private const string Library = @"C:\Windows\System32\winsqlite3.dll";
    private const int OpenReadWriteCreateFullMutex = 0x00000002 | 0x00000004 | 0x00010000;
    private const int Row = 100;
    private const int Done = 101;
    private IntPtr db;

    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)]
    private static extern int sqlite3_open_v2(
        byte[] filename, out IntPtr database, int flags, IntPtr vfs);

    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)]
    private static extern int sqlite3_close(IntPtr database);

    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)]
    private static extern int sqlite3_busy_timeout(IntPtr database, int milliseconds);

    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)]
    private static extern int sqlite3_exec(
        IntPtr database, byte[] sql, IntPtr callback, IntPtr arg,
        out IntPtr errorMessage);

    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)]
    private static extern void sqlite3_free(IntPtr pointer);

    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr sqlite3_errmsg(IntPtr database);

    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)]
    private static extern int sqlite3_prepare_v2(
        IntPtr database, byte[] sql, int byteCount, out IntPtr statement,
        IntPtr tail);

    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)]
    private static extern int sqlite3_bind_text(
        IntPtr statement, int index, byte[] text, int byteCount,
        IntPtr destructor);

    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)]
    private static extern int sqlite3_step(IntPtr statement);

    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr sqlite3_column_text(IntPtr statement, int column);

    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)]
    private static extern int sqlite3_column_bytes(IntPtr statement, int column);

    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)]
    private static extern int sqlite3_finalize(IntPtr statement);

    private static byte[] Utf8Z(string value)
    {
        if (value == null || value.IndexOf('\0') >= 0)
            throw new ArgumentException("SQLite input invalid");
        return Encoding.UTF8.GetBytes(value + "\0");
    }

    private static string Utf8Pointer(IntPtr pointer, int length)
    {
        if (pointer == IntPtr.Zero || length < 0)
            return null;
        byte[] bytes = new byte[length];
        Marshal.Copy(pointer, bytes, 0, length);
        return Encoding.UTF8.GetString(bytes);
    }

    private void Check(int result)
    {
        if (result != 0)
            throw new InvalidOperationException(
                "SQLite failure " + result + ": " +
                Utf8Pointer(sqlite3_errmsg(db), MessageLength(sqlite3_errmsg(db))));
    }

    private static int MessageLength(IntPtr pointer)
    {
        if (pointer == IntPtr.Zero)
            return 0;
        int count = 0;
        while (count < 1024 && Marshal.ReadByte(pointer, count) != 0)
            count++;
        return count;
    }

    internal Ea4eProtectedSqlite(string path)
    {
        if (String.IsNullOrWhiteSpace(path) || !Path.IsPathRooted(path))
            throw new ArgumentException("Absolute SQLite path required");
        int result = sqlite3_open_v2(
            Utf8Z(path), out db, OpenReadWriteCreateFullMutex, IntPtr.Zero);
        try
        {
            Check(result);
            Check(sqlite3_busy_timeout(db, 1000));
            Execute("PRAGMA foreign_keys = ON");
            Execute("PRAGMA journal_mode = DELETE");
            Execute("PRAGMA synchronous = FULL");
            using (var journal = Prepare("PRAGMA journal_mode"))
            {
                if (!journal.Step() || journal.Text(0) != "delete")
                    throw new InvalidOperationException("SQLite journal mode denied");
            }
            using (var sync = Prepare("PRAGMA synchronous"))
            {
                if (!sync.Step() || sync.Text(0) != "2")
                    throw new InvalidOperationException("SQLite sync mode denied");
            }
        }
        catch
        {
            Dispose();
            throw;
        }
    }

    // Schema and transaction constants only; request data goes through BindText.
    internal void Execute(string sql)
    {
        IntPtr error;
        int result = sqlite3_exec(
            db, Utf8Z(sql), IntPtr.Zero, IntPtr.Zero, out error);
        if (error != IntPtr.Zero)
            sqlite3_free(error);
        Check(result);
    }

    internal Statement Prepare(string sql)
    {
        IntPtr statement;
        byte[] bytes = Utf8Z(sql);
        Check(sqlite3_prepare_v2(db, bytes, bytes.Length, out statement,
                                 IntPtr.Zero));
        if (statement == IntPtr.Zero)
            throw new InvalidOperationException("Empty SQLite statement");
        return new Statement(this, statement);
    }

    public void Dispose()
    {
        if (db == IntPtr.Zero)
            return;
        IntPtr closing = db;
        db = IntPtr.Zero;
        if (sqlite3_close(closing) != 0)
            throw new InvalidOperationException("SQLite close failed");
    }

    internal sealed class Statement : IDisposable
    {
        private readonly Ea4eProtectedSqlite owner;
        private IntPtr statement;

        internal Statement(Ea4eProtectedSqlite owner, IntPtr statement)
        {
            this.owner = owner;
            this.statement = statement;
        }

        internal void BindText(int index, string value)
        {
            byte[] bytes = Utf8Z(value);
            owner.Check(sqlite3_bind_text(
                statement, index, bytes, bytes.Length - 1, new IntPtr(-1)));
        }

        internal bool Step()
        {
            int result = sqlite3_step(statement);
            if (result == Row)
                return true;
            if (result == Done)
                return false;
            owner.Check(result);
            throw new InvalidOperationException("SQLite step failed");
        }

        internal string Text(int column)
        {
            IntPtr pointer = sqlite3_column_text(statement, column);
            return Utf8Pointer(pointer, sqlite3_column_bytes(statement, column));
        }

        public void Dispose()
        {
            if (statement == IntPtr.Zero)
                return;
            IntPtr closing = statement;
            statement = IntPtr.Zero;
            owner.Check(sqlite3_finalize(closing));
        }
    }
}
