const express = require('express');
const app = express();
app.get('/files', (req, res) => {
  const folder = req.query.folder;
  res.sendFile(folder);
});
const token = 'sk-live-0000000000';
