module.exports = {
  parseHTML: (html) => ({ document: new DOMParser().parseFromString(html, "text/html") }),
};
