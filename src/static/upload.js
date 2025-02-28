document.getElementById('file-upload').addEventListener('change', function () {
    var files = this.files;
    if (files.length === 0) return;

    var formData = new FormData();
    for (var i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }

    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/admin/upload', true);

    xhr.upload.onprogress = function (event) {
        if (event.lengthComputable) {
            var percentComplete = (event.loaded / event.total) * 100;
            document.getElementById('upload-progress').value = percentComplete;
            document.getElementById('progress-text').innerText = Math.round(percentComplete) + '%';
        }
    };

    xhr.onload = function () {
        if (xhr.status === 303 || xhr.status === 200) {
            window.location.href = '/admin';
        } else {
            alert('Ошибка загрузки: ' + xhr.responseText);
            document.getElementById('upload-progress').value = 0;
            document.getElementById('progress-text').innerText = '0%';
        }
    };

    xhr.onerror = function () {
        alert('Произошла ошибка при загрузке файлов.');
    };

    document.getElementById('progress-container').style.display = 'block';
    xhr.send(formData);
});