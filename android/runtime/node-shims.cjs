function checked(result) {
  const value = JSON.parse(result);
  if (value.error) throw new Error(value.error);
  return value.value;
}
module.exports = {
  existsSync: (name) => checked(NativeRuntime.file("exists", name, "")),
  readFileSync: (name) => checked(NativeRuntime.file("read", name, "")),
  writeFileSync: (name, value) => checked(NativeRuntime.file("write", name, String(value))),
  mkdirSync() {},
  join: (...parts) => parts.join("/"),
  dirname: (value) => value.slice(0, value.lastIndexOf("/")),
  createHash: () => ({
    update(value) {
      return { digest: () => NativeRuntime.sha256(String(value)) };
    },
  }),
};
