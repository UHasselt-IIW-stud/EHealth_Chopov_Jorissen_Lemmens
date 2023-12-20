var measurementStarted = true;

// JavaScript function to toggle measurement
function toggleMeasurement() {
    var measurementButton = document.querySelector('button');

        var form = document.getElementById("userForm");
        var formData = new FormData(form);

        fetch("/submit", {
            method: "POST",
            body: formData
        })
        // Toggle measurement state
        measurementStarted = !measurementStarted;

        if (measurementStarted) {
            measurementButton.textContent = 'Stop Measurement';
            // Add code here to handle starting measurement if needed

        } else {
            measurementButton.textContent = 'Start Measurement';
            // Add code here to handle stopping measurement if needed
        }  
}