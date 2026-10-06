#Requires -Version 7.4
<#
Pinned resource acquisition and plain-file ZIP/TAR/TAR.GZ extraction.
LibraryOnly loads the same implementation for offline transport fixtures; it does
not acquire a resource. This script never installs or executes its output.
#>
[CmdletBinding()]
param(
    [ValidateSet('Download', 'Extract')][string]$Mode = 'Extract',
    [string]$RunRoot, [string]$Destination, [string]$ManifestOut,
    [string]$ExpectedSha256, [long]$ExpectedSize,
    [string]$Uri, [string]$Archive,
    [ValidateSet('Zip', 'Tar', 'TarGzip')][string]$Format = 'Zip',
    [string[]]$AllowedTopLevel,
    [int]$MaxMembers = 20000,
    [long]$MaxMemberBytes = 536870912,
    [long]$MaxTotalBytes = 2147483648,
    [switch]$LibraryOnly
)
$ErrorActionPreference = 'Stop'
if (-not $IsWindows -or [Environment]::Version.Major -lt 8) {
    throw 'Requires Windows, PowerShell 7.4+ and .NET 8+.'
}
if (-not ('CommPlan.DeliveryAssets' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;

namespace CommPlan {
public sealed class AssetOptions {
    public string Mode = "Extract", RunRoot, Destination, ManifestOut;
    public string ExpectedSha256, Uri, Archive, Format = "Zip";
    public string[] AllowedTopLevel;
    public long ExpectedSize, MaxMemberBytes = 536870912, MaxTotalBytes = 2147483648;
    public int MaxMembers = 20000;
}
public sealed class AssetMember {
    public string Path { get; set; }
    public string Type { get; set; }
    public long Size { get; set; }
    public string Sha256 { get; set; }
}
public sealed class AssetManifest {
    public int SchemaVersion { get; set; } = 1;
    public string Mode { get; set; }
    public string Status { get; set; }
    public string StartedUtc { get; set; }
    public string FinishedUtc { get; set; }
    public string EvidenceKind { get; set; }
    public string Source { get; set; }
    public string Destination { get; set; }
    public long ExpectedSize { get; set; }
    public long? ActualSize { get; set; }
    public string ExpectedSha256 { get; set; }
    public string ActualSha256 { get; set; }
    public int MaxMembers { get; set; }
    public long MaxMemberBytes { get; set; }
    public long MaxTotalBytes { get; set; }
    public int MemberCount { get; set; }
    public long TotalBytes { get; set; }
    public List<AssetMember> Members { get; set; } = new List<AssetMember>();
    public string Error { get; set; }
}
public static class DeliveryAssets {
    const long MetadataLimit = 16777216;
    const int PaxRecordLimit = 1048576;
    static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);
    static readonly JsonSerializerOptions Json = new JsonSerializerOptions {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase, WriteIndented = true
    };
    static string Now() { return DateTime.UtcNow.ToString("O"); }
    static void Require(bool ok, string why) { if (!ok) throw new InvalidDataException(why); }
    static bool Exists(string path) {
        try { File.GetAttributes(path); return true; }
        catch (FileNotFoundException) { return false; }
        catch (DirectoryNotFoundException) { return false; }
    }
    static void CheckAncestors(string path) {
        for (string p = path; p != null; p = Path.GetDirectoryName(p)) {
            if (!Exists(p)) continue;
            var attrs = File.GetAttributes(p);
            Require((attrs & FileAttributes.ReparsePoint) == 0, "reparse point: " + p);
            Require(p == path || (attrs & FileAttributes.Directory) != 0, "parent is not directory: " + p);
        }
    }
    static bool Inside(string path, string parent) {
        return path.StartsWith(parent.TrimEnd('\\') + "\\", StringComparison.OrdinalIgnoreCase);
    }
    static string LocalAbsolute(string path) {
        Require(!String.IsNullOrWhiteSpace(path) && Regex.IsMatch(path, @"^[A-Za-z]:[\\/]"), "absolute local path required");
        Require(!path.Substring(2).Contains(':') && !path.Any(c => c < 32), "unsafe local path");
        string absolute = Path.GetFullPath(path);
        string relative = absolute.Substring(3).TrimEnd('\\').Replace('\\','/');
        if (relative.Length > 0) SafeName(relative,false);
        return absolute;
    }
    static Uri DownloadUri(string text) {
        Uri uri;
        Require(System.Uri.TryCreate(text, UriKind.Absolute, out uri) && uri.Scheme == "https"
            && String.IsNullOrEmpty(uri.UserInfo) && String.IsNullOrEmpty(uri.Fragment)
            && !Regex.IsMatch(uri.AbsolutePath, @"(^|/)latest(/|$)", RegexOptions.IgnoreCase), "fixed HTTPS URI required");
        return uri;
    }
    static void Validate(AssetOptions o) {
        Require(o.Mode == "Extract" || o.Mode == "Download", "invalid mode");
        Require(o.ExpectedSize > 0 && Regex.IsMatch(o.ExpectedSha256 ?? "", @"\A[0-9a-fA-F]{64}\z"), "positive size and SHA256 required");
        Require(o.MaxMembers > 0 && o.MaxMemberBytes > 0 && o.MaxTotalBytes > 0, "positive limits required");
        // Checked up front: the TAR read budget includes payload, headers and padding.
        checked { long budget = o.MaxTotalBytes + ((long)o.MaxMembers * 1024) + 10240; }
        o.ExpectedSha256 = o.ExpectedSha256.ToLowerInvariant();
        o.RunRoot = LocalAbsolute(o.RunRoot).TrimEnd('\\');
        Require(o.RunRoot.Length > 3 && Directory.Exists(o.RunRoot), "existing non-volume run root required");
        o.Destination = LocalAbsolute(o.Destination);
        o.ManifestOut = LocalAbsolute(o.ManifestOut);
        CheckAncestors(o.RunRoot); CheckAncestors(o.Destination); CheckAncestors(o.ManifestOut);
        Require(Inside(o.Destination, o.RunRoot) && Inside(o.ManifestOut, o.RunRoot), "output outside run root");
        Require(!o.Destination.Equals(o.ManifestOut, StringComparison.OrdinalIgnoreCase)
            && !Inside(o.ManifestOut, o.Destination) && !Inside(o.Destination, o.ManifestOut), "overlapping outputs");
        Require(!Exists(o.Destination) && !Exists(o.ManifestOut), "output already exists");
        if (o.Mode == "Download") {
            DownloadUri(o.Uri);
            Require(String.IsNullOrEmpty(o.Archive) && (o.AllowedTopLevel == null || o.AllowedTopLevel.Length == 0), "extract parameters in download mode");
        } else {
            Require(String.IsNullOrEmpty(o.Uri), "download URI in extract mode");
            Require(o.Format == "Zip" || o.Format == "Tar" || o.Format == "TarGzip", "unsupported archive format");
            o.Archive = LocalAbsolute(o.Archive); CheckAncestors(o.Archive);
            Require(Inside(o.Archive, o.RunRoot) && File.Exists(o.Archive), "ordinary archive inside run root required");
            Require(!o.Archive.Equals(o.Destination, StringComparison.OrdinalIgnoreCase)
                && !o.Archive.Equals(o.ManifestOut, StringComparison.OrdinalIgnoreCase)
                && !Inside(o.Archive, o.Destination) && !Inside(o.Destination, o.Archive)
                && !Inside(o.ManifestOut, o.Archive), "input/output overlap");
            Require(o.AllowedTopLevel != null && o.AllowedTopLevel.Length > 0, "literal top-level allowlist required");
            foreach (string top in o.AllowedTopLevel) {
                Require(SafeName(top, false) == top && !top.Contains('/'), "invalid top-level allowlist");
            }
            Require(o.AllowedTopLevel.Distinct(StringComparer.OrdinalIgnoreCase).Count() == o.AllowedTopLevel.Length, "duplicate top-level allowlist");
        }
    }
    static void MakeDirectory(string path) {
        CheckAncestors(path); Directory.CreateDirectory(path); CheckAncestors(path);
    }
    static string SafeName(string name, bool directory) {
        Require(!String.IsNullOrEmpty(name) && name.Length <= 32760, "empty/long archive path");
        if (directory && name.EndsWith("/", StringComparison.Ordinal)) name = name.Substring(0, name.Length - 1);
        Require(!name.StartsWith("/") && !name.Contains('\\') && !name.Contains(':')
            && name == name.Normalize(NormalizationForm.FormC), "unsafe archive path: " + name);
        foreach (string part in name.Split('/')) {
            Require(part.Length > 0 && part != "." && part != ".." && !part.EndsWith(".") && !part.EndsWith(" ")
                && !part.Any(c => c < 32 || c == 127 || "<>\"|?*".Contains(c)), "unsafe archive component: " + name);
            string stem = part.Split('.')[0].TrimEnd(' ', '.');
            Require(!Regex.IsMatch(stem, @"\A(CON|PRN|AUX|NUL|CLOCK\$|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])\z", RegexOptions.IgnoreCase), "reserved device name: " + name);
        }
        return name;
    }
    sealed class Scan {
        public readonly List<AssetMember> Members = new List<AssetMember>();
        readonly Dictionary<string, bool> Paths = new Dictionary<string, bool>(StringComparer.OrdinalIgnoreCase);
        readonly HashSet<string> Explicit = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        public int Count; public long Total;
        public void Charge(AssetOptions o, long bytes) {
            Require(++Count <= o.MaxMembers, "member count limit exceeded");
            Require(bytes >= 0 && bytes <= o.MaxMemberBytes, "member byte limit exceeded");
            Total = checked(Total + bytes); Require(Total <= o.MaxTotalBytes, "total byte limit exceeded");
        }
        public string Register(AssetOptions o, string raw, bool dir) {
            string name = SafeName(raw, dir);
            Require(o.AllowedTopLevel.Contains(name.Split('/')[0], StringComparer.OrdinalIgnoreCase), "unapproved top-level member: " + name);
            Require(Explicit.Add(name), "duplicate member: " + name);
            bool previous;
            Require(!Paths.TryGetValue(name, out previous) || (previous && dir), "file/directory collision: " + name);
            Paths[name] = dir;
            string parent = name;
            while (parent.Contains('/')) {
                parent = parent.Substring(0, parent.LastIndexOf('/'));
                Require(!Paths.TryGetValue(parent, out previous) || previous, "parent is a file: " + name);
                Paths[parent] = true;
            }
            return name;
        }
    }
    static string FileSha(Stream stream) {
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }
    static string MemberOutput(string stage, string name, bool directory) {
        if (stage == null) return null;
        string path = Path.GetFullPath(Path.Combine(stage, name.Replace('/', '\\')));
        Require(Inside(path, stage), "member outside staging root");
        if (directory) MakeDirectory(path); else MakeDirectory(Path.GetDirectoryName(path));
        CheckAncestors(path); Require(directory || !Exists(path), "member output exists");
        return path;
    }
    static readonly uint[] CrcTable = MakeCrcTable();
    static uint[] MakeCrcTable() {
        var table = new uint[256];
        for (uint i=0; i<256; i++) { uint x=i; for (int bit=0; bit<8; bit++) x=(x>>1)^((x&1)!=0 ? 0xEDB88320U : 0U); table[i]=x; }
        return table;
    }
    static string CopyExact(Stream source, Stream destination, long size, bool expectEof, out uint crc, bool computeCrc=false, CancellationToken token=default) {
        var buffer = new byte[65536]; long bytes = 0; uint checksum = UInt32.MaxValue;
        using (var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256)) {
            while (bytes < size) {
                int wanted = (int)Math.Min(buffer.Length, size - bytes);
                int n = token.CanBeCanceled ? source.ReadAsync(buffer.AsMemory(0,wanted),token).AsTask().GetAwaiter().GetResult() : source.Read(buffer,0,wanted);
                Require(n > 0, "truncated member/resource");
                bytes = checked(bytes + n); hash.AppendData(buffer, 0, n); destination.Write(buffer, 0, n);
                if (computeCrc) for (int i = 0; i < n; i++) checksum = (checksum >> 8) ^ CrcTable[(checksum ^ buffer[i]) & 255];
            }
            if (expectEof) {
                int extra = token.CanBeCanceled ? source.ReadAsync(buffer.AsMemory(0,1),token).AsTask().GetAwaiter().GetResult() : source.Read(buffer,0,1);
                Require(extra == 0, "resource/member longer than expected");
            }
            crc = ~checksum;
            return Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
        }
    }
    static AssetMember CopyMember(Stream data, Scan scan, AssetOptions o, string name, bool directory, long size, string stage, uint? crc = null) {
        scan.Charge(o, size); string path = scan.Register(o, name, directory);
        Require(!directory || size == 0, "directory has content");
        string output = MemberOutput(stage, path, directory);
        var member = new AssetMember { Path = path, Type = directory ? "directory" : "file", Size = size };
        if (!directory) {
            using (Stream target = output == null ? Stream.Null : new FileStream(output, FileMode.CreateNew, FileAccess.Write, FileShare.None)) {
                uint actualCrc; member.Sha256 = CopyExact(data, target, size, false, out actualCrc,crc.HasValue);
                Require(!crc.HasValue || crc.Value == actualCrc, "ZIP CRC mismatch");
            }
        }
        scan.Members.Add(member); return member;
    }
    static byte[] ReadExact(Stream stream, int length) {
        var bytes = new byte[length]; int offset = 0;
        while (offset < length) { int n = stream.Read(bytes, offset, length - offset); Require(n > 0, "truncated archive"); offset += n; }
        return bytes;
    }
    static void SkipExact(Stream stream, long length) {
        var buffer = new byte[8192];
        while (length > 0) { int n = stream.Read(buffer, 0, (int)Math.Min(buffer.Length, length)); Require(n > 0, "truncated archive padding"); length -= n; }
    }
    sealed class BoundStream : Stream {
        readonly Stream Inner; readonly long Limit; long Bytes;
        public BoundStream(Stream inner, long limit) { Inner = inner; Limit = limit; }
        public override int Read(byte[] b, int o, int c) { int n = Inner.Read(b, o, (int)Math.Min(c, Math.Max(1, Limit - Bytes + (Limit == Int64.MaxValue ? 0 : 1)))); Bytes = checked(Bytes + n); Require(Bytes <= Limit, "decompressed byte limit exceeded"); return n; }
        public override bool CanRead => true; public override bool CanSeek => false; public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException(); public override long Position { get => Bytes; set => throw new NotSupportedException(); }
        public override void Flush() {} public override long Seek(long o, SeekOrigin s) => throw new NotSupportedException();
        public override void SetLength(long v) => throw new NotSupportedException(); public override void Write(byte[] b, int o, int c) => throw new NotSupportedException();
    }
    static long Octal(byte[] block, int offset, int length) {
        Require((block[offset] & 0x80) == 0, "unsupported TAR base-256 number");
        string text = Encoding.ASCII.GetString(block, offset, length).Trim('\0', ' ');
        if (text.Length == 0) return 0;
        long value = 0; foreach (char c in text) { Require(c >= '0' && c <= '7', "invalid TAR number"); value = checked(value * 8 + c - '0'); } return value;
    }
    static string Text(byte[] b, int o, int n) {
        int length = Array.IndexOf(b, (byte)0, o, n); return Utf8.GetString(b, o, length < 0 ? n : length - o);
    }
    static Dictionary<string,string> Pax(byte[] bytes) {
        var values = new Dictionary<string,string>(); int offset = 0;
        while (offset < bytes.Length) {
            int space = Array.IndexOf(bytes, (byte)' ', offset); Require(space > offset && space - offset < 10, "invalid PAX record length");
            int length; Require(Int32.TryParse(Encoding.ASCII.GetString(bytes, offset, space-offset), NumberStyles.None, CultureInfo.InvariantCulture, out length)
                && length > space-offset+2 && length <= bytes.Length-offset && bytes[offset+length-1] == 10, "invalid PAX record");
            string text = Utf8.GetString(bytes, space+1, offset+length-space-2); int equal = text.IndexOf('='); Require(equal > 0, "invalid PAX key");
            string key = text.Substring(0,equal), value = text.Substring(equal+1);
            Require(new [] {"path", "size", "mtime", "atime", "ctime", "uid", "gid", "uname", "gname", "comment"}.Contains(key), "unsupported PAX key: " + key);
            Require(!values.ContainsKey(key), "duplicate PAX key"); values[key] = value; offset += length;
        }
        return values;
    }
    static Scan ScanTar(Stream file, AssetOptions o, string stage) {
        Stream input = o.Format == "TarGzip" ? new GZipStream(file, CompressionMode.Decompress, true) : file;
        try {
            var data = new BoundStream(input, checked(o.MaxTotalBytes + (long)o.MaxMembers*1024 + 10240));
            var scan = new Scan(); var pending = new Dictionary<string,string>();
            while (true) {
                byte[] header = ReadExact(data, 512);
                if (header.All(b => b == 0)) {
                    Require(ReadExact(data,512).All(b => b == 0) && pending.Count == 0, "invalid TAR termination");
                    var padding = new byte[8192]; int n;
                    while ((n = data.Read(padding,0,padding.Length)) != 0) Require(padding.Take(n).All(b => b == 0), "data after TAR termination");
                    return scan;
                }
                long checksum = Octal(header,148,8), sum = 0;
                for (int i=0; i<512; i++) sum += i >= 148 && i < 156 ? 32 : header[i];
                Require(checksum == sum, "TAR checksum mismatch");
                byte type = header[156]; long rawSize = Octal(header,124,12);
                string name = Text(header,0,100), prefix = Text(header,345,155);
                if (prefix.Length > 0) name = prefix + "/" + name;
                Require(Text(header,157,100).Length == 0, "TAR link target not permitted");
                if (type == (byte)'x' || type == (byte)'g' || type == (byte)'L') {
                    scan.Charge(o, rawSize); Require(rawSize <= PaxRecordLimit, "TAR metadata byte limit exceeded");
                    byte[] content = ReadExact(data, checked((int)rawSize)); SkipExact(data,(512-rawSize%512)%512);
                    Require(pending.Count == 0, "stacked TAR path metadata unsupported");
                    if (type == (byte)'L') { string longName = Utf8.GetString(content).TrimEnd('\0'); pending["path"] = longName; }
                    else {
                        var values = Pax(content);
                        if (type == (byte)'g') Require(!values.ContainsKey("path") && !values.ContainsKey("size"), "global PAX path/size not permitted");
                        else pending = values;
                    }
                    continue;
                }
                Require(type == 0 || type == (byte)'0' || type == (byte)'5', "TAR link/special member not permitted");
                if (pending.ContainsKey("path")) name = pending["path"];
                long size = rawSize;
                if (pending.ContainsKey("size")) Require(Int64.TryParse(pending["size"], NumberStyles.None, CultureInfo.InvariantCulture, out size), "invalid PAX size");
                pending.Clear();
                CopyMember(data,scan,o,name,type == (byte)'5',size,stage);
                SkipExact(data,(512-size%512)%512);
            }
        } finally { if (input != file) input.Dispose(); }
    }
    sealed class ZipMeta { public uint Crc; public long Size; public uint Attributes; public ushort MadeBy; }
    static List<ZipMeta> ZipMetadata(Stream file, AssetOptions o) {
        Require(file.Length >= 22, "truncated ZIP");
        int tailSize = (int)Math.Min(file.Length,65557); file.Position = file.Length-tailSize;
        byte[] tail = ReadExact(file,tailSize); int end = -1;
        for (int i=tail.Length-22; i>=0; i--) if (BitConverter.ToUInt32(tail,i) == 0x06054b50 && i+22+BitConverter.ToUInt16(tail,i+20) == tail.Length) { end=i; break; }
        Require(end >= 0, "ZIP end record missing");
        ushort count = BitConverter.ToUInt16(tail,end+10);
        Require(BitConverter.ToUInt16(tail,end+4) == 0 && BitConverter.ToUInt16(tail,end+6) == 0
            && BitConverter.ToUInt16(tail,end+8) == count && count != UInt16.MaxValue, "multipart/ZIP64 not supported");
        uint length = BitConverter.ToUInt32(tail,end+12), start = BitConverter.ToUInt32(tail,end+16);
        Require(count <= o.MaxMembers && length <= MetadataLimit && (long)start+length == file.Length-tailSize+end, "ZIP central metadata limit/layout invalid");
        file.Position = start; var result = new List<ZipMeta>();
        for (int i=0; i<count; i++) {
            var header = ReadExact(file,46); Require(BitConverter.ToUInt32(header,0) == 0x02014b50, "invalid ZIP central member");
            ushort flags = BitConverter.ToUInt16(header,8), method = BitConverter.ToUInt16(header,10);
            Require((flags & 1) == 0 && (method == 0 || method == 8), "encrypted/unsupported ZIP member");
            uint compressed = BitConverter.ToUInt32(header,20), size = BitConverter.ToUInt32(header,24), local = BitConverter.ToUInt32(header,42);
            Require(compressed != UInt32.MaxValue && size != UInt32.MaxValue && local < start && BitConverter.ToUInt16(header,34) == 0, "ZIP64/member layout unsupported");
            Require(size <= o.MaxMemberBytes, "member byte limit exceeded");
            int variable = BitConverter.ToUInt16(header,28) + BitConverter.ToUInt16(header,30) + BitConverter.ToUInt16(header,32);
            Require(file.Position+variable <= (long)start+length, "ZIP metadata outside central directory"); SkipExact(file,variable);
            result.Add(new ZipMeta { Crc=BitConverter.ToUInt32(header,16), Size=size, Attributes=BitConverter.ToUInt32(header,38), MadeBy=BitConverter.ToUInt16(header,4) });
        }
        Require(file.Position == (long)start+length, "ZIP central count mismatch"); file.Position = 0; return result;
    }
    static Scan ScanZip(Stream file, AssetOptions o, string stage) {
        var metadata = ZipMetadata(file,o); var scan = new Scan();
        using (var zip = new ZipArchive(file,ZipArchiveMode.Read,true)) {
            Require(zip.Entries.Count == metadata.Count, "ZIP member count mismatch");
            for (int i=0; i<metadata.Count; i++) {
                var member = zip.Entries[i]; var meta = metadata[i]; bool directory = member.FullName.EndsWith("/");
                int unixType = (int)((meta.Attributes >> 16) & 0xF000);
                Require((meta.Attributes & (uint)FileAttributes.ReparsePoint) == 0
                    && (unixType == 0 || unixType == (directory ? 0x4000 : 0x8000)), "ZIP link/special member not permitted");
                Require((meta.Attributes & (uint)FileAttributes.Directory) == 0 || directory, "ZIP directory marker mismatch");
                Require(member.Length == meta.Size, "ZIP member size mismatch");
                using (var data = member.Open()) {
                    CopyMember(data,scan,o,member.FullName,directory,member.Length,stage,meta.Crc);
                    Require(data.ReadByte() == -1, "ZIP member longer than declared");
                }
            }
        }
        return scan;
    }
    static void InputHash(Stream file, AssetOptions o, AssetManifest manifest) {
        manifest.ActualSize = file.Length; Require(file.Length == o.ExpectedSize, "input size mismatch");
        file.Position = 0; manifest.ActualSha256 = FileSha(file);
        Require(manifest.ActualSha256 == o.ExpectedSha256, "input SHA256 mismatch"); file.Position = 0;
    }
    static void Extract(AssetOptions o, AssetManifest manifest) {
        using (var file = new FileStream(o.Archive,FileMode.Open,FileAccess.Read,FileShare.Read)) {
            InputHash(file,o,manifest);
            Scan plan = o.Format == "Zip" ? ScanZip(file,o,null) : ScanTar(file,o,null);
            Require(plan.Members.Count > 0, "empty archive");
            string stage = o.Destination + ".partial-" + Guid.NewGuid().ToString("N");
            Require(!Exists(stage), "staging already exists"); MakeDirectory(stage); file.Position = 0;
            Scan actual = o.Format == "Zip" ? ScanZip(file,o,stage) : ScanTar(file,o,stage);
            Require(JsonSerializer.Serialize(plan.Members) == JsonSerializer.Serialize(actual.Members), "archive changed between passes");
            InputHash(file,o,manifest); CheckAncestors(o.Destination); Require(!Exists(o.Destination), "output appeared during extraction");
            Directory.Move(stage,o.Destination);
            manifest.MemberCount = actual.Count; manifest.TotalBytes = actual.Total; manifest.Members = actual.Members;
        }
    }
    static void AcquireContent(AssetOptions o, AssetManifest manifest, Stream content, CancellationToken token=default) {
        string partial = o.Destination + ".partial-" + Guid.NewGuid().ToString("N");
        MakeDirectory(Path.GetDirectoryName(partial)); CheckAncestors(partial);
        using (var output = new FileStream(partial,FileMode.CreateNew,FileAccess.Write,FileShare.None)) {
            uint unused; manifest.ActualSha256 = CopyExact(content,output,o.ExpectedSize,true,out unused,false,token); manifest.ActualSize = output.Length;
        }
        Require(manifest.ActualSha256 == o.ExpectedSha256, "download SHA256 mismatch");
        CheckAncestors(o.Destination); File.Move(partial,o.Destination,false);
    }
    static void Download(AssetOptions o, AssetManifest manifest) {
        Uri uri = DownloadUri(o.Uri);
        using (var handler = new HttpClientHandler { AllowAutoRedirect=false, UseCookies=false, UseDefaultCredentials=false })
        using (var client = new HttpClient(handler) { Timeout=TimeSpan.FromMinutes(30) })
        using (var deadline = new CancellationTokenSource(TimeSpan.FromMinutes(30))) {
            for (int redirects=0; redirects<=5; redirects++) {
                using (var request = new HttpRequestMessage(HttpMethod.Get,uri)) {
                    request.Headers.AcceptEncoding.ParseAdd("identity");
                    using (var response = client.Send(request,HttpCompletionOption.ResponseHeadersRead,deadline.Token)) {
                        int code = (int)response.StatusCode;
                        if (code == 301 || code == 302 || code == 303 || code == 307 || code == 308) {
                            Require(redirects < 5 && response.Headers.Location != null, "redirect limit/location invalid");
                            uri = DownloadUri(new Uri(uri,response.Headers.Location).AbsoluteUri); continue;
                        }
                        response.EnsureSuccessStatusCode();
                        Require(response.Content.Headers.ContentLength == null || response.Content.Headers.ContentLength == o.ExpectedSize, "HTTP content length mismatch");
                        Require(!response.Content.Headers.ContentEncoding.Any(c => c != "identity"), "HTTP encoded body not permitted");
                        manifest.Source = uri.GetLeftPart(UriPartial.Path);
                        using (var data = response.Content.ReadAsStream(deadline.Token)) AcquireContent(o,manifest,data,deadline.Token);
                        return;
                    }
                }
            }
        }
    }
    static AssetManifest RunWithManifest(AssetOptions o, Stream fixture) {
        Validate(o); MakeDirectory(Path.GetDirectoryName(o.ManifestOut));
        var manifest = new AssetManifest {
            Mode=o.Mode, Status="FAILED", StartedUtc=Now(), Destination=o.Destination,
            Source=o.Mode == "Download" ? DownloadUri(o.Uri).GetLeftPart(UriPartial.Path) : o.Archive,
            ExpectedSize=o.ExpectedSize, ExpectedSha256=o.ExpectedSha256, MaxMembers=o.MaxMembers,
            MaxMemberBytes=o.MaxMemberBytes, MaxTotalBytes=o.MaxTotalBytes,
            EvidenceKind=fixture == null ? (o.Mode == "Download" ? "HTTPS_DOWNLOAD" : "LOCAL_ARCHIVE") : "TRANSPORT_FIXTURE"
        };
        using (var evidence = new FileStream(o.ManifestOut,FileMode.CreateNew,FileAccess.Write,FileShare.None)) {
            try {
                if (fixture != null) { Require(o.Mode == "Download", "transport fixture requires download mode"); AcquireContent(o,manifest,fixture); }
                else if (o.Mode == "Download") Download(o,manifest); else Extract(o,manifest);
                manifest.Status = "PASSED"; return manifest;
            } catch (Exception ex) { manifest.Error = ex.Message; throw; }
            finally {
                manifest.FinishedUtc = Now(); byte[] text = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(manifest,Json)); evidence.Write(text,0,text.Length);
            }
        }
    }
    public static AssetManifest Run(AssetOptions o) { return RunWithManifest(o,null); }
    public static AssetManifest FromFixtureStream(AssetOptions o, Stream input) {
        if (input == null) throw new ArgumentNullException(nameof(input)); return RunWithManifest(o,input);
    }
}
}
'@
}
if ($LibraryOnly) { return }
$options = [CommPlan.AssetOptions]::new()
foreach ($name in 'Mode','RunRoot','Destination','ManifestOut','ExpectedSha256','ExpectedSize',
    'Uri','Archive','Format','AllowedTopLevel','MaxMembers','MaxMemberBytes','MaxTotalBytes') {
    $options.$name = Get-Variable -Name $name -ValueOnly
}
try {
    [CommPlan.DeliveryAssets]::Run($options) | ConvertTo-Json -Depth 6
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
