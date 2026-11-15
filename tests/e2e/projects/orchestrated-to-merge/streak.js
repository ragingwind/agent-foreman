// The number of days in a row, counted back from the last one, that are done.
function streak(days) {
  let n = 0;
  for (let i = days.length - 1; i >= 0 && days[i]; i--) n++;
  return n;
}

module.exports = { streak };
