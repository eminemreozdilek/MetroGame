import cv2
import numpy as np


def generate_gradient_with_random_slopes(input_file, output_file):
    # Load the image in grayscale (0=black, 255=white)
    img = cv2.imread(input_file, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("Image not found or unable to load.")

    # Binarize the image:
    # Assuming white (255) represents soils (land) and black (0) represents seas.
    # Pixels with value > 127 become 255 (land) and the rest become 0 (sea).
    ret, binary = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)

    # Compute the distance transform.
    # For every land (white) pixel, compute its Euclidean distance to the nearest sea (black) pixel.
    dist_transform = cv2.distanceTransform(binary, cv2.DIST_L2, 5)

    # Normalize the distance transform to the range [0, 1]
    max_dist = np.max(dist_transform)
    if max_dist > 0:
        norm_dist = dist_transform / max_dist
    else:
        norm_dist = dist_transform

    norm_dist = norm_dist ** 2
    norm_dist = -1.5 * norm_dist ** 3 + 2 * norm_dist**2 + 0.5 * norm_dist

    gradient = norm_dist

    gradient = np.clip(gradient, 0, 1)

    # Convert the gradient to an 8-bit grayscale image (0-255)
    gradient_img = (gradient * 65535).astype(np.uint16)

    # Ensure sea areas remain black by using the original binary mask.
    gradient_img[binary == 0] = 0
    # Save the resulting image
    cv2.imwrite(output_file, gradient_img)
    print(f"Gradient map saved as {output_file}")



if __name__ == '__main__':
    # Replace 'map.png' with your input PNG file.
    input_file = 'example.png'
    output_file = 'gradient_map.tif'
    # Adjust the alpha value for more or less randomness and final_blur_kernel for blur intensity.
    generate_gradient_with_random_slopes(input_file, output_file)
