// A lower-case, dash-separated slug of a title.
function slug(title) {
  return title.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

module.exports = { slug };
